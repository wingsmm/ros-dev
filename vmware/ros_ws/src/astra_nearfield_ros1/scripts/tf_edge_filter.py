#!/usr/bin/env python2
"""Filter bag TF remaps: drop only the two camera extrinsic edges."""

from __future__ import print_function

import json
import sys
import threading

TARGET_EDGES = (
    ("base_footprint", "camera_link"),
    ("camera_link", "camera_depth_optical_frame"),
)
TARGET_CHILDREN = frozenset(edge[1] for edge in TARGET_EDGES)
TARGET_EDGE_SET = frozenset(TARGET_EDGES)


def normalize_frame(value):
    return str(value or "").lstrip("/")


def classify_edge(parent, child):
    """Return 'drop', 'keep', or 'anomaly' for one transform edge."""
    parent = normalize_frame(parent)
    child = normalize_frame(child)
    if (parent, child) in TARGET_EDGE_SET:
        return "drop"
    if child in TARGET_CHILDREN:
        # Same child frame under an unexpected parent: keep for TF guard.
        return "anomaly"
    return "keep"


def filter_transforms(transforms):
    """Split transform-like objects into (kept, dropped, anomaly_count).

    Anomaly edges are included in kept so CameraTfGuard can conflict.
    Each item needs .header.frame_id and .child_frame_id.
    """
    kept = []
    dropped = []
    anomaly_count = 0
    for transform in transforms:
        decision = classify_edge(
            transform.header.frame_id, transform.child_frame_id
        )
        if decision == "drop":
            dropped.append(transform)
        elif decision == "anomaly":
            anomaly_count += 1
            kept.append(transform)
        else:
            kept.append(transform)
    return kept, dropped, anomaly_count


def _run_node():
    import rospy
    from std_msgs.msg import String
    from tf2_msgs.msg import TFMessage

    class TfEdgeFilter(object):
        def __init__(self):
            self.lock = threading.Lock()
            self.received = 0
            self.kept = 0
            self.dropped = 0
            self.anomaly = 0
            self.empty_skipped = 0
            self.static_by_child = {}

            self.pub_tf = rospy.Publisher("/tf", TFMessage, queue_size=100)
            self.pub_static = rospy.Publisher(
                "/tf_static", TFMessage, queue_size=100, latch=True
            )
            self.pub_stats = rospy.Publisher(
                "~stats", String, queue_size=1, latch=True
            )

            rospy.Subscriber("/bag/tf", TFMessage, self._on_tf, queue_size=100)
            rospy.Subscriber(
                "/bag/tf_static", TFMessage, self._on_static, queue_size=100
            )
            self._publish_stats()

        def _publish_stats(self):
            payload = {
                "received": self.received,
                "kept": self.kept,
                "dropped": self.dropped,
                "anomaly": self.anomaly,
                "empty_skipped": self.empty_skipped,
                "static_cached": len(self.static_by_child),
            }
            self.pub_stats.publish(
                String(data=json.dumps(payload, sort_keys=True))
            )

        def _on_tf(self, message):
            kept, dropped, anomaly = filter_transforms(message.transforms)
            with self.lock:
                self.received += len(message.transforms)
                self.kept += len(kept)
                self.dropped += len(dropped)
                self.anomaly += anomaly
                if not kept:
                    self.empty_skipped += 1
                    self._publish_stats()
                    return
                out = TFMessage(transforms=kept)
                self._publish_stats()
            self.pub_tf.publish(out)

        def _on_static(self, message):
            kept, dropped, anomaly = filter_transforms(message.transforms)
            with self.lock:
                self.received += len(message.transforms)
                self.dropped += len(dropped)
                self.anomaly += anomaly
                for transform in kept:
                    child = normalize_frame(transform.child_frame_id)
                    self.static_by_child[child] = transform
                    self.kept += 1
                if not self.static_by_child:
                    self.empty_skipped += 1
                    self._publish_stats()
                    return
                out = TFMessage(transforms=list(self.static_by_child.values()))
                self._publish_stats()
            self.pub_static.publish(out)

    rospy.init_node("astra_tf_edge_filter")
    TfEdgeFilter()
    rospy.loginfo(
        "tf_edge_filter ready: /bag/tf -> /tf, /bag/tf_static -> /tf_static"
    )
    rospy.spin()
    return 0


def main():
    return _run_node()


if __name__ == "__main__":
    sys.exit(main())
