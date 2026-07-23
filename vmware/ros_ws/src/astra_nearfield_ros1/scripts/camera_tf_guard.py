#!/usr/bin/env python2
"""Own and continuously guard the two Astra camera TF edges."""

from __future__ import print_function

import math
import sys
import threading
import time

import rospy
import tf2_ros
from geometry_msgs.msg import TransformStamped
from tf.transformations import quaternion_from_euler
from tf2_msgs.msg import TFMessage

try:
    STRING_TYPES = (basestring,)
except NameError:
    STRING_TYPES = (str,)


def _frame(value):
    return str(value or "").lstrip("/")


def _array_param(name, size):
    value = rospy.get_param(name)
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError("%s must contain %d values" % (name, size))
    return [float(item) for item in value]


def _bool_param(name, default):
    value = rospy.get_param(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, STRING_TYPES):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _distance(left, right):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def _transform_matches(actual, expected, translation_tolerance, rotation_tolerance):
    if (
        _frame(actual.header.frame_id) != _frame(expected.header.frame_id)
        or _frame(actual.child_frame_id) != _frame(expected.child_frame_id)
    ):
        return False
    actual_translation = (
        actual.transform.translation.x,
        actual.transform.translation.y,
        actual.transform.translation.z,
    )
    expected_translation = (
        expected.transform.translation.x,
        expected.transform.translation.y,
        expected.transform.translation.z,
    )
    actual_rotation = (
        actual.transform.rotation.x,
        actual.transform.rotation.y,
        actual.transform.rotation.z,
        actual.transform.rotation.w,
    )
    expected_rotation = (
        expected.transform.rotation.x,
        expected.transform.rotation.y,
        expected.transform.rotation.z,
        expected.transform.rotation.w,
    )
    rotation_distance = min(
        _distance(actual_rotation, expected_rotation),
        _distance(actual_rotation, tuple(-value for value in expected_rotation)),
    )
    return (
        _distance(actual_translation, expected_translation) <= translation_tolerance
        and rotation_distance <= rotation_tolerance
    )


def _make_transform(parent, child, xyz, rpy):
    transform = TransformStamped()
    transform.header.frame_id = parent
    transform.child_frame_id = child
    transform.transform.translation.x = xyz[0]
    transform.transform.translation.y = xyz[1]
    transform.transform.translation.z = xyz[2]
    quaternion = quaternion_from_euler(rpy[0], rpy[1], rpy[2])
    transform.transform.rotation.x = quaternion[0]
    transform.transform.rotation.y = quaternion[1]
    transform.transform.rotation.z = quaternion[2]
    transform.transform.rotation.w = quaternion[3]
    return transform


class CameraTfGuard(object):
    def __init__(self):
        self.node_name = rospy.get_name()
        self.reuse_existing = _bool_param("~reuse_existing_tf", False)
        self.preflight_duration = max(
            0.2, float(rospy.get_param("~preflight_duration_s", 1.5))
        )
        self.translation_tolerance = max(
            0.0, float(rospy.get_param("~translation_tolerance_m", 0.001))
        )
        self.rotation_tolerance = max(
            0.0, float(rospy.get_param("~rotation_tolerance", 0.001))
        )

        parent = _frame(rospy.get_param("~parent_frame"))
        camera = _frame(rospy.get_param("~camera_frame"))
        optical = _frame(rospy.get_param("~optical_frame"))
        if not parent or not camera or not optical:
            raise ValueError("parent_frame, camera_frame and optical_frame are required")
        if len(set((parent, camera, optical))) != 3:
            raise ValueError("camera TF frames must be distinct")

        self.expected = {
            (parent, camera): _make_transform(
                parent,
                camera,
                _array_param("~xyz_m", 3),
                _array_param("~rpy_rad", 3),
            ),
            (camera, optical): _make_transform(
                camera,
                optical,
                _array_param("~optical_xyz_m", 3),
                _array_param("~optical_rpy_rad", 3),
            ),
        }
        self.expected_by_child = dict((edge[1], edge) for edge in self.expected)
        self.observed = dict((edge, {}) for edge in self.expected)
        self.allowed_external = dict((edge, set()) for edge in self.expected)
        self.lock = threading.Lock()
        self.active = False
        self.conflict = False
        self.broadcaster = tf2_ros.StaticTransformBroadcaster()
        self.tf_subscriber = rospy.Subscriber(
            "/tf", TFMessage, self._on_tf, queue_size=100
        )
        self.tf_static_subscriber = rospy.Subscriber(
            "/tf_static", TFMessage, self._on_tf, queue_size=100
        )

    def _on_tf(self, message):
        header = getattr(message, "_connection_header", {}) or {}
        caller = header.get("callerid", "<unknown>")
        for transform in message.transforms:
            child = _frame(transform.child_frame_id)
            edge = self.expected_by_child.get(child)
            if edge is None:
                continue
            with self.lock:
                self.observed[edge][caller] = transform
                external_conflict = (
                    self.active
                    and caller != self.node_name
                    and caller not in self.allowed_external[edge]
                )
            if external_conflict:
                self.conflict = True
                rospy.logfatal(
                    "TF ownership conflict after startup: %s -> %s from %s",
                    edge[0],
                    edge[1],
                    caller,
                )
                rospy.signal_shutdown("camera TF ownership conflict")

    def _claim_under_lock(self):
        """Evaluate observed publishers and flip active while holding the lock.

        Returns (ok, to_publish). When ok is False the caller must not publish.
        """
        to_publish = []
        for edge, expected in self.expected.items():
            authorities = dict(self.observed[edge])
            if not authorities:
                to_publish.append(expected)
                continue
            callers = sorted(authorities)
            if not self.reuse_existing:
                rospy.logfatal(
                    "Refusing to start: TF %s -> %s already published by %s. "
                    "Disable VMware Qt TF and driver publish_tf.",
                    edge[0],
                    edge[1],
                    ", ".join(callers),
                )
                return False, []
            if len(callers) != 1:
                rospy.logfatal(
                    "Cannot reuse TF %s -> %s: multiple publishers %s",
                    edge[0],
                    edge[1],
                    ", ".join(callers),
                )
                return False, []
            caller = callers[0]
            if not _transform_matches(
                authorities[caller],
                expected,
                self.translation_tolerance,
                self.rotation_tolerance,
            ):
                rospy.logfatal(
                    "Cannot reuse TF %s -> %s from %s: value differs from YAML",
                    edge[0],
                    edge[1],
                    caller,
                )
                return False, []
            self.allowed_external[edge].add(caller)
            rospy.logwarn(
                "Debug reuse enabled for TF %s -> %s from %s",
                edge[0],
                edge[1],
                caller,
            )

        # Ownership becomes active before unlock/publish so any publisher that
        # appears in the gap is treated as a conflict by _on_tf.
        self.active = True
        return True, to_publish

    def start(self):
        rospy.loginfo(
            "Sampling /tf and /tf_static for %.2fs before claiming camera TF",
            self.preflight_duration,
        )
        time.sleep(self.preflight_duration)

        with self.lock:
            ok, to_publish = self._claim_under_lock()
        if not ok:
            return False

        if to_publish:
            now = rospy.Time.now()
            for transform in to_publish:
                transform.header.stamp = now
            self.broadcaster.sendTransform(to_publish)
            for transform in to_publish:
                rospy.loginfo(
                    "Owning static TF %s -> %s",
                    transform.header.frame_id,
                    transform.child_frame_id,
                )
        return True


def _validate_extrinsics_status():
    status = str(rospy.get_param("~status", "provisional")).strip().lower()
    allow_provisional = _bool_param("~allow_provisional", False)
    physical = _bool_param("~physical_measurement", False)

    if status == "provisional":
        if not allow_provisional:
            rospy.logfatal(
                "Extrinsics status is 'provisional'; use allow_provisional:=true "
                "only for local/debug work, or set status to nominal/measured."
            )
            return False
        rospy.logwarn("Running with provisional extrinsics (debug only)")
        return True

    if status == "nominal":
        if physical:
            rospy.logfatal(
                "status=nominal cannot set physical_measurement:=true; "
                "use status=measured only after on-robot measurement."
            )
            return False
        rospy.logwarn(
            "Extrinsics status=nominal (factory/product pose). "
            "Software wiring acceptance only; not physical calibration PASS."
        )
        return True

    if status == "measured":
        if not physical:
            rospy.logfatal(
                "status=measured requires physical_measurement:=true and "
                "recorded uncertainty in the extrinsics YAML."
            )
            return False
        rospy.loginfo("Extrinsics status=measured (physical acceptance path)")
        return True

    rospy.logfatal(
        "Unknown extrinsics status %r; allowed: provisional, nominal, measured",
        status,
    )
    return False


def main():
    rospy.init_node("astra_camera_tf_guard", anonymous=False)
    if not _validate_extrinsics_status():
        return 2
    try:
        guard = CameraTfGuard()
    except (KeyError, TypeError, ValueError) as exc:
        rospy.logfatal("Invalid camera extrinsics configuration: %s", exc)
        return 2
    if not guard.start():
        return 2
    rospy.spin()
    return 3 if guard.conflict else 0


if __name__ == "__main__":
    sys.exit(main())
