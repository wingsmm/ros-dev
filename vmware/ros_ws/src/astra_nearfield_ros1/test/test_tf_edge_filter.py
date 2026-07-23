#!/usr/bin/env python2
"""Unit tests for tf_edge_filter pure helpers (no ROS Master required)."""

from __future__ import print_function

import os
import sys
import unittest

# Allow `python2 test_tf_edge_filter.py` from any cwd.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from tf_edge_filter import (  # noqa: E402
    classify_edge,
    filter_transforms,
    normalize_frame,
)


class FakeHeader(object):
    def __init__(self, frame_id):
        self.frame_id = frame_id


class FakeTransform(object):
    def __init__(self, parent, child):
        self.header = FakeHeader(parent)
        self.child_frame_id = child


class TfEdgeFilterLogicTest(unittest.TestCase):
    def test_normalize_leading_slash(self):
        self.assertEqual(normalize_frame("/base_footprint"), "base_footprint")
        self.assertEqual(normalize_frame("camera_link"), "camera_link")
        self.assertEqual(normalize_frame(""), "")

    def test_drop_target_edges(self):
        self.assertEqual(
            classify_edge("base_footprint", "camera_link"), "drop"
        )
        self.assertEqual(
            classify_edge("/camera_link", "/camera_depth_optical_frame"),
            "drop",
        )

    def test_keep_ordinary_edges(self):
        self.assertEqual(classify_edge("odom", "base_footprint"), "keep")
        self.assertEqual(classify_edge("map", "odom"), "keep")

    def test_anomaly_same_child_wrong_parent(self):
        self.assertEqual(classify_edge("odom", "camera_link"), "anomaly")
        self.assertEqual(
            classify_edge("base_link", "camera_depth_optical_frame"),
            "anomaly",
        )

    def test_mixed_message_drops_only_targets(self):
        transforms = [
            FakeTransform("odom", "base_footprint"),
            FakeTransform("base_footprint", "camera_link"),
            FakeTransform("camera_link", "camera_depth_optical_frame"),
            FakeTransform("base_footprint", "laser"),
        ]
        kept, dropped, anomaly = filter_transforms(transforms)
        self.assertEqual(anomaly, 0)
        self.assertEqual(len(dropped), 2)
        kept_pairs = [
            (normalize_frame(t.header.frame_id), normalize_frame(t.child_frame_id))
            for t in kept
        ]
        dropped_pairs = [
            (normalize_frame(t.header.frame_id), normalize_frame(t.child_frame_id))
            for t in dropped
        ]
        self.assertEqual(
            kept_pairs,
            [("odom", "base_footprint"), ("base_footprint", "laser")],
        )
        self.assertEqual(
            dropped_pairs,
            [
                ("base_footprint", "camera_link"),
                ("camera_link", "camera_depth_optical_frame"),
            ],
        )

    def test_empty_message(self):
        kept, dropped, anomaly = filter_transforms([])
        self.assertEqual(kept, [])
        self.assertEqual(dropped, [])
        self.assertEqual(anomaly, 0)

    def test_anomaly_kept_for_guard(self):
        transforms = [FakeTransform("odom", "camera_link")]
        kept, dropped, anomaly = filter_transforms(transforms)
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(dropped), 0)
        self.assertEqual(anomaly, 1)

    def test_static_accumulate_logic(self):
        """Simulate static cache: later messages must not drop earlier kept edges."""
        cache = {}
        batches = [
            [FakeTransform("odom", "base_footprint")],
            [FakeTransform("base_footprint", "laser")],
            [FakeTransform("base_footprint", "camera_link")],  # dropped
        ]
        for batch in batches:
            kept, _dropped, _anomaly = filter_transforms(batch)
            for transform in kept:
                cache[normalize_frame(transform.child_frame_id)] = transform
        self.assertEqual(sorted(cache.keys()), ["base_footprint", "laser"])
        self.assertNotIn("camera_link", cache)


if __name__ == "__main__":
    unittest.main(verbosity=2)
