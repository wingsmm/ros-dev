# RobotCA Android App

This directory contains the Android/RobotCA source tree, local build tools, APK outputs, and app-specific documentation.

## Layout

| Path | Responsibility |
|------|----------------|
| `RobotCA-master/RobotCA-master/` | Upstream RobotCA Android source tree used by this project. |
| `scripts/` | Android App local build/install scripts only. |
| `apks/` | Built APK artifacts copied out of the Gradle project. |
| `docs/` | Android App design notes and feature documents. |
| `tools/` | Local Android/rosjava build dependencies. |

Robot-side ROS startup and status scripts live under `../xtark/scripts/`, because they operate the robot ROS stack rather than the Android build output.

## Current APK

Recommended package:

```text
cn.xtark.robotca
```

Recommended APK output:

```text
apks\xtark-control-alt-debug.apk
```

The original RobotCA release package name is:

```text
com.robotca.ControlApp
```

The rebuilt APK intentionally uses `cn.xtark.robotca` by default so it does not overwrite the original release package.

## Build

From `android/`:

```bat
scripts\build_app.bat
```

The build script validates:

- local JDK8 under `tools\jdk8`
- Android SDK under `D:\ProgramData\Android\sdk`
- local rosjava Maven repo under `tools\rosjava_mvn_repo`
- RobotCA Gradle project layout and package id support
- generated `local.properties`
- Gradle build output
- collected APK package and launcher metadata through `aapt`

Default output:

```text
apks\xtark-control-alt-debug.apk
```

To build with the original release package name:

```bat
scripts\build_app.bat orig
```

That writes:

```text
apks\xtark-control-debug.apk
```

## Install To MuMu

From `android/`:

```bat
scripts\install_mumu.bat
```

This uninstalls `cn.xtark.robotca` if present, then installs:

```text
apks\xtark-control-alt-debug.apk
```

## Robot-Side Android Validation

Robot:

```text
192.168.1.168
xtark / xtark
```

From the repository root on Windows:

```bat
xtark\scripts\android_remote.bat all
xtark\scripts\android_remote.bat status
```

`android_remote.bat deploy` syncs `xtark/scripts/android_stack.sh` and the `xtark_nav` ROS package to the robot. `android_remote.bat start` (or `all`) starts the Android validation stack without re-uploading unless you run `deploy` first.

The robot-side script starts roscore, `xtark_bringup.launch`, camera, gmapping, move_base, `/robot_pose_in_map`, and Android navigation speed sync. It deliberately does not start `json_base_adapter`, which is for PC/Qt control and can conflict on `/cmd_vel`.

On the Android App, use this ROS Master URI:

```text
http://192.168.1.168:11311
```

## Launcher Note

The original release launcher is:

```text
com.robotca.ControlApp.ControlApp
```

The rebuilt APK launches:

```text
com.robotca.ControlApp.RobotChooser
```

Cold-starting `ControlApp` directly can crash when `ROBOT_INFO` is empty. Starting at `RobotChooser` allows normal app entry and testing.

## SLAM Map And A-B-A Navigation

The SLAM map page includes A/B navigation controls:

```text
Set A, Set B, Go B, Return A, A-B-A, Cancel, Center
```

Flow:

```text
Android selects a white free cell
-> SlamMapView converts screen coordinates to map coordinates
-> isFreeForGoal() checks the target and safety radius
-> RobotController publishes /move_base_simple/goal
-> RobotController subscribes /move_base/status
-> SlamMapFragment updates state from SUCCEEDED / ABORTED / REJECTED / PREEMPTED
```

Current behavior:

- A/B points are drawn on the map.
- Targets must be in white free space, with roughly three safe surrounding grid cells.
- The yellow gmapping bounds are a visual/debug reference, not a hard limit.
- A-B-A depends on robot-side `move_base`, which `android_stack.sh start` launches by default.
- `/robot_pose_in_map` is started by `xtark_nav/launch/robot_pose_in_map.launch` and is used for map overlay pose display.

## Manual Control And SafeMode

Manual buttons and the joystick share this velocity path:

```text
ManualControlFragment / JoystickView
-> RobotController.forceVelocity()
-> /cmd_vel
-> xtark_driver
```

RobotCA SafeMode is not full autonomous obstacle avoidance. It is a front collision warning and speed reduction path:

- `WarningSystem` reads the front laser sector, about +/-40 degrees.
- Nearby front obstacles raise `warnAmount` and make the HUD red.
- With SafeMode enabled, forward speed is reduced by `(1 - warnAmount)^2`.
- High `warnAmount` can make forward motion feel blocked while reverse or turning still works.

If forward motion feels weak, check `/cmd_vel` on the robot. If `linear.x` is much smaller than the configured manual speed, Android SafeMode already clipped the command before publishing.

More detail:

```text
docs\Android手动控制与SafeMode说明.md
```

## Script Summary

| Script | Responsibility |
|--------|----------------|
| `scripts\build_app.bat` | Build RobotCA, defaulting to the non-conflicting `cn.xtark.robotca` package. |
| `scripts\install_mumu.bat` | Install the rebuilt APK into MuMu. |
| `..\xtark\scripts\android_remote.bat` | Deploy, start, stop, status, logs for the robot-side Android validation stack. |
| `..\xtark\scripts\android_stack.sh` | Canonical robot-side Android validation startup script. |

## Upstream References

```text
https://github.com/rosjava/android_apps
https://github.com/SCCapstone/RobotCA
```
