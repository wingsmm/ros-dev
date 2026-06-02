# SLAM System ROS 2 Code

This `src` tree contains the project-owned ROS 2 packages. Vendored third-party source belongs in the sibling `../third` directory. See `../SLAM系统方案.md`.

Packages:

- `slam_frontend`: self-contained lightweight LiDAR odometry frontend for validation.
- `slam_perception`: stair detection and climb trigger state machine.
- `slam_bringup`: launch files for TF, sensors orchestration, mapping/localization modes, obstacle scan.

## Workspace policy

- **Do not** depend on remote workspaces such as `~/ros2_ws` or `~/slam_ws` for project functionality.
- If a third-party function is needed, vendor a pinned copy into the repository root `third/` directory and maintain it here.
- **Do not** colocate or colcon-build this project with remote third-party trees (`unitree_lidar_*`, `point_lio`, SAM-QN, etc.).
- Default frontend mode uses this repository's `slam_frontend`, not remote `point_lio`.
- Remote install path: **TBD** (separate from `~/ros2_ws` and `~/slam_ws`).
- Remote workspaces may be used only as inspected references or temporary manual comparison, not as default runtime dependencies.
- Do not deploy, upload, sync, push, or overwrite remote files without explicit user approval in the current conversation.
- Canonical local docs are `../SLAM系统方案.md` and `../项目备忘.md`.

## Build (local or remote, own workspace)

```bash
cd other
source /opt/ros/humble/setup.bash
colcon build --symlink-install --base-paths src --packages-select slam_frontend slam_perception slam_bringup
source install/setup.bash
```

When vendored ROS packages are added under `third/`, build from the repository root with:

```bash
colcon build --symlink-install --base-paths src third
```

## Run

```bash
ros2 launch slam_bringup system.launch.py mode:=frontend
ros2 launch slam_perception perception.launch.py
```
