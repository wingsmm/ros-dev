# astra_nearfield_ros1

ROS1 Melodic adapter for the isolated Astra near-field experiment. Stage A
owns camera extrinsics status and strict TF ownership; perception algorithms
are intentionally deferred.

## Extrinsics status contract

| `status` | Meaning | Guard behavior |
|----------|---------|----------------|
| `provisional` | Untrusted placeholder | Needs `allow_provisional:=true` (debug only) |
| `nominal` | Factory / product install pose, not tape-measured on this unit | Allowed for **software wiring** acceptance only |
| `measured` | On-robot measurement with uncertainty recorded | Requires `physical_measurement: true`; formal physical path |

Current checked-in YAML is **`nominal`** (copied from robot factory bringup).
That is **not** physical calibration PASS.

## Stage A startup

1. On the robot, use the experiment profile so the Astra driver does not
   publish its own camera TF:

   ```bash
   ~/ros_ws/scripts/pc_stack.sh camera-nearfield-start
   ~/ros_ws/scripts/pc_stack.sh camera-nearfield-check
   ```

   Check must verify the **live** depth launch argv `publish_tf:=0` (not only
   the profile variable). Switching from `camera` / `camera_deep` restarts the
   depth driver when `publish_tf` changes.

2. Keep `config/astra_extrinsics.yaml` accurate:
   - `status: nominal` + `physical_measurement: false` for product pose;
   - `status: measured` only after measuring this chassis and recording
     uncertainty, with `physical_measurement: true`.

   Parent frame on this xtark chassis is **`base_footprint`** (there is no
   `base_link` edge in the live TF tree).

3. On VMware, disable the Qt-owned TF before starting Qt:

   ```bash
   export CAMERA_TF_ENABLE=0
   ```

4. Start the sole owner of both camera edges:

   ```bash
   roslaunch astra_nearfield_ros1 camera_tf.launch
   ```

The launch fails if either `base_footprint -> camera_link` or
`camera_link -> camera_depth_optical_frame` already exists on `/tf` or
`/tf_static` (unless debug `reuse_existing_tf:=true`). After a locked claim,
it keeps monitoring and exits if an external publisher later claims either
edge.

For local wiring checks with untrusted zeros only:

```bash
roslaunch astra_nearfield_ros1 camera_tf.launch allow_provisional:=true
```

## Stage A acceptance boundary

Package presence / compile is not runtime validation.

**Software closed-loop PASS (status=nominal, recorded 2026-07-23):**

- robot `camera-nearfield-check` live `publish_tf:=0`;
- unique TF ownership by `astra_camera_tf_guard`;
- `/vmware/depth/points` publishing;
- RViz Fixed Frame=`base_footprint`;
- directional check: front / left / right / ground-ish / 60s stable — OK.

**Near blind zone (expected):**

- software filter: `CAMERA_POINTCLOUD_MIN_RANGE_M=0.25`;
- Astra Pro hardware: depth weak/empty roughly inside 0.4-0.6 m.

**Still not claimed:**

- physical extrinsics PASS (`status: measured` + uncertainty);
- obstacle / drop / step perception.

```text
STAGE A SOFTWARE CLOSED-LOOP PASS (nominal extrinsics)
NEAR BLIND ZONE DOCUMENTED
PHYSICAL EXTRINSICS NOT MEASURED
```
