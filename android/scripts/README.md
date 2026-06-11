# Android 脚本说明

Windows 侧只保留这几条 `.bat`，机器人端统一用 `run_android.sh`。

## Windows 脚本（`android/scripts/`）

| 脚本 | 用途 |
|------|------|
| `build_robotca_super.bat` | **部署** — 编译 APK |
| `deploy_mumu_alt.bat` | **部署** — 安装 APK 到 MuMu |
| `status_android_169.bat` | **查看** — 169 上 ROS 状态、节点、日志 |
| `start_android_169.bat` | 同步 `run_android.sh` 到 169 并远程执行（默认 `start`，可传 `stop` / `status`） |

常用命令（在 `android` 目录下）：

```bat
scripts\build_robotca_super.bat
scripts\deploy_mumu_alt.bat
scripts\status_android_169.bat
scripts\start_android_169.bat
scripts\start_android_169.bat stop
```

## 机器人端（169）

只需一条脚本，SSH 上去直接跑：

```bash
/home/xtark/ros_ws/scripts/run_android.sh start
/home/xtark/ros_ws/scripts/run_android.sh stop
/home/xtark/ros_ws/scripts/run_android.sh status
/home/xtark/ros_ws/scripts/run_android.sh watch-nav
/home/xtark/ros_ws/scripts/run_android.sh logs
```

规范源文件：`xtark/scripts/run_android.sh`（`start` 会顺带拉起 gmapping、move_base、App 导航速度同步等，无需再跑其他脚本）。
