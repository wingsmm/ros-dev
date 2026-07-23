# astra_nearfield_ros1

ROS1 Melodic adapter for the isolated Astra near-field experiment.

- **Stage A**: extrinsics status + strict camera TF ownership
- **Stage B**: robot-side bag capture + VM isolated replay (no perception)

## Extrinsics status contract

| `status` | Meaning | Guard behavior |
|----------|---------|----------------|
| `provisional` | Untrusted placeholder | Needs `allow_provisional:=true` (debug only) |
| `nominal` | Factory / product install pose, not tape-measured on this unit | Allowed for **software wiring** acceptance only |
| `measured` | On-robot measurement with uncertainty recorded | Requires `physical_measurement: true`; formal physical path |

Current checked-in YAML is **`nominal`**.

## Stage A startup

1. Robot: `~/ros_ws/scripts/pc_stack.sh camera-nearfield-start` then `camera-nearfield-check`
2. VM (online Master path): `CAMERA_TF_ENABLE=0` then `roslaunch astra_nearfield_ros1 camera_tf.launch`

## Stage B1: capture on robot 168

Deploy:

```bat
xtark\scripts\pc_stack_remote.bat deploy
```

On robot (after nearfield stack is up):

```bash
~/ros_ws/scripts/astra_capture.sh start \
  --scene flat_floor \
  --lighting indoor_day \
  --camera-state stationary \
  --duration 60
~/ros_ws/scripts/astra_capture.sh inspect ~/xtark_logs/astra_nearfield/bags/<id>
```

Bags land under `~/xtark_logs/astra_nearfield/bags/` with `capture.bag`, `manifest.json`, `rosbag_info.txt`.

## Stage B2: isolated replay on VM 154

Deploy package (does **not** change default Qt `deploy`):

```bat
vmware\scripts\vm_qt_remote.bat astra-deploy
```

On VM:

```bash
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
REPLAY=$(rosrun astra_nearfield_ros1 astra_replay.sh 2>/dev/null | head -n0)
# Prefer explicit path:
~/ros_ws/devel/lib/astra_nearfield_ros1/astra_replay.sh check /path/to/capture.bag
~/ros_ws/devel/lib/astra_nearfield_ros1/astra_replay.sh raw /path/to/capture.bag
~/ros_ws/devel/lib/astra_nearfield_ros1/astra_replay.sh cloud /path/to/capture.bag
~/ros_ws/devel/lib/astra_nearfield_ros1/astra_replay.sh stop
```

Hard constraints:

- Master is forced to `http://127.0.0.1:11321`
- `/use_sim_time=true` + `rosbag play --clock --rate 0.5`
- `/tf` and `/tf_static` remapped to `/bag/*`, then `tf_edge_filter` strips only:
  - `base_footprint -> camera_link`
  - `camera_link -> camera_depth_optical_frame`
- Cloud mode republishes camera edges from nominal YAML via `camera_tf_guard`
- Point cloud script default: `~/ros-dev/vmware/qt/scripts/sparse_depth_pointcloud.py`

**Nearfield bags may drop 0 camera TF edges** (driver `publish_tf:=0`). That is normal.
Synthetic unit tests must still prove both target edges are deleted.

`perception` mode is reserved; not implemented in Stage B.

## Unit tests (no Master)

```bash
python2 $(rospack find astra_nearfield_ros1)/../src/astra_nearfield_ros1/test/test_tf_edge_filter.py
# or from checkout:
python2 vmware/ros_ws/src/astra_nearfield_ros1/test/test_tf_edge_filter.py
```

## Stage A acceptance label

```text
STAGE A SOFTWARE CLOSED-LOOP PASS (nominal extrinsics)
```

Physical extrinsics PASS and perception algorithms remain out of scope.
