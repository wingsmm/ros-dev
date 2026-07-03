# VMware 虚拟开发环境说明

本文档基于 **2026-07-03** 对 `xtark@192.168.1.154`（`xtark-vmpc`）的 SSH 实探测，梳理塔克官方 VMware 虚拟机与真机 `xtark-robot` 的分工，重点说明 VM 上 `~/ros_ws` 的内容与用法。

真机登录与 ROS 网络见 [xtark/docs/远端登录.md](../../xtark/docs/远端登录.md)；真机硬件与传感器见 [xtark/docs/远端硬件与传感器.md](../../xtark/docs/远端硬件与传感器.md)。

---

## 1. 两台机器怎么分工

| 项目 | 真机 `xtark-robot` | VMware 虚拟机 `xtark-vmpc` |
|------|-------------------|---------------------------|
| 主机名 | `xtark-robot` | `xtark-vmpc` |
| IP | `192.168.1.169` | `192.168.1.154` |
| 平台 | Jetson Nano / aarch64 | VMware 虚拟机 / x86_64 |
| 内核 | `4.9.201-tegra` | `5.3.0-28-generic` |
| 系统 | Ubuntu 18.04.5 LTS | Ubuntu 18.04.5 LTS |
| ROS | Melodic | Melodic（约 256 个 deb 包） |
| 角色 | **ROS Master**、驱动、SLAM、导航、相机、JSON 桥 | **开发终端**：RViz、键盘/手柄遥控，连真机 Master |
| `~/ros_ws` 体量 | ~1.4 GB（完整业务包 + scripts） | ~1.8 MB（出厂精简工作空间） |
| 登录后提示 | 含 `ROBOT TYPE: MEC` | 只显示 `ROS Master URI` / `ROS IP`，无机型变量 |

关系示意：

```text
Windows PC ──SSH──► xtark-vmpc (154)          RViz / 键盘遥控
                         │
                         │  ROS_MASTER_URI → 192.168.1.169:11311
                         ▼
                    xtark-robot (169)         roscore / 驱动 / SLAM / move_base
```

VM 不跑 Master，也不承载本仓库同步上去的 `xtark_json_bridge`、`xtark_nav` 等包；那些在真机 `~/ros_ws` 上。

---

## 2. 连接信息

| 项目 | 值 |
|------|-----|
| IP | `192.168.1.154` |
| SSH 用户 | `xtark`（密码与真机相同） |
| 网卡 | `ens33`，DHCP 获取 `192.168.1.154/24` |
| 主机密钥（ED25519） | `SHA256:PtzWE2T7/bY7TdqIzyfTc7bJuifo0PjA4BEaorV0odA` |

```powershell
ping 192.168.1.154
ssh xtark@192.168.1.154
```

登录成功后会看到塔克 ASCII 横幅，以及：

```text
ROS Master URI: http://192.168.1.169:11311
ROS IP: 192.168.1.154
```

若 VM 与机器人不在同一网段，启动脚本会打印黄色警告（见 `/usr/share/xtark/xtark_vmwareStartup.sh`）。

### plink 一次性命令

```powershell
$plink = "C:\Program Files\PuTTY\plink.exe"
$hostkey = "SHA256:PtzWE2T7/bY7TdqIzyfTc7bJuifo0PjA4BEaorV0odA"

& $plink -batch -hostkey $hostkey xtark@192.168.1.154 "hostname; ls ~/ros_ws/src"
```

VM 内已配置 `alias sshrobot='ssh xtark@$ROBOT_IP'`，可快速 SSH 到真机（`ROBOT_IP=192.168.1.169`）。

---

## 3. ROS 环境（`~/.bashrc`）

VM 登录时自动执行：

```bash
export LIBGL_ALWAYS_SOFTWARE=1          # VMware 下 OpenGL 软件渲染
interface=ens33
export IPAddress=`ifconfig $interface | grep -o 'inet [^ ]*' | cut -d " " -f2`

source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash

export ROBOT_IP=192.168.1.169            # 机器人 IP，换机时改这里
alias sshrobot='ssh xtark@$ROBOT_IP'

export ROS_IP=$IPAddress                 # 本机 VM IP（154）
export ROS_MASTER_URI=http://$ROBOT_IP:11311

bash /usr/share/xtark/xtark_vmwareStartup.sh $ROS_MASTER_URI $ROS_IP
```

要点：

- **`ROS_MASTER_URI` 指向真机 169**，不是 154。
- **`ROS_IP` 是本机 VM 地址**，供 RViz、遥控节点向 Master 注册。
- 真机若改 IP，需同步改 VM 的 `ROBOT_IP`。
- 与 [xtark/docs/远端登录.md](../../xtark/docs/远端登录.md) 中 PC 侧设置相同：`ROS_MASTER_URI` 指机器人，`ROS_IP` 指本机。

---

## 4. `~/ros_ws` 目录结构（VM）

```
~/ros_ws/
├── .catkin_workspace
├── build/          # catkin 编译产物（2020-04-27）
├── devel/          # 含 setup.bash，已编译
└── src/
    ├── CMakeLists.txt
    ├── xtark_ctl/      # 键盘 / 手柄遥控
    └── xtark_viz/      # RViz 配置文件
```

**没有** `scripts/`、`tools/`、`record/`，也**没有**本仓库维护的 `xtark_driver`、`xtark_nav`、`xtark_json_bridge` 等包。

### 4.1 `xtark_ctl` — 遥控

| 路径 | 说明 |
|------|------|
| `scripts/xtark_twist_keyboard.py` | 键盘发布 `/cmd_vel` |
| `scripts/xtark_twist_joy.py` | 手柄遥控 |
| `launch/xtark_keyboard.launch` | 启动键盘节点 |
| `launch/xtark_joy.launch` | 启动手柄节点 |

常用：

```bash
# 需真机已启动驱动（或至少 roscore + 底盘节点）
roslaunch xtark_ctl xtark_keyboard.launch

# 或直接
rosrun xtark_ctl xtark_twist_keyboard.py
```

### 4.2 `xtark_viz` — RViz 配置

`rviz/` 下预置场景（连接真机话题后选用）：

| 文件 | 用途 |
|------|------|
| `xtark_mapping.rviz` | 建图 |
| `xtark_nav.rviz` | 导航 |
| `xtark_cartographer.rviz` | Cartographer |
| `xtark_rtabmapping.rviz` / `xtark_rtabnav.rviz` | RTAB-Map |
| `xtark_orb.rviz` | ORB 视觉 |
| `xtark_ar_track.rviz` | AR 跟踪 |
| `xtark_multirobot.rviz` | 多机 |

```bash
rviz -d ~/ros_ws/src/xtark_viz/rviz/xtark_mapping.rviz
```

---

## 5. 与真机 `~/ros_ws` 对比

真机 `xtark@192.168.1.169` 上的 `~/ros_ws/src`（2026-07-03 实测）：

```text
third_packages
xtark_apps
xtark_audio
xtark_ctl
xtark_cv
xtark_depth_preview      ← 本仓库维护
xtark_driver
xtark_json_bridge        ← 本仓库维护
xtark_laser_odometry     ← 本仓库维护
xtark_nav                  ← 本仓库维护
xtark_nav_depthcamera
```

真机另有 `~/ros_ws/scripts/`（`android_stack.sh`、`qt_stack.sh`、`json_stack.sh` 等），由本仓库 `xtark/scripts/` 部署。

| 操作 | 应在哪里做 |
|------|-----------|
| 部署/编译 `xtark_json_bridge`、`xtark_nav` 等 | **真机 169** |
| `android_stack.sh` / `qt_stack.sh` 启停栈 | **真机 169** |
| RViz 看 `/scan`、`/map` | **VM 154** 或 Windows PC（装 Melodic） |
| 键盘遥控 `/cmd_vel` | **VM 154**（`xtark_ctl`）或真机本地 |
| 改导航参数、保存地图 | **真机 169** |

本仓库 Windows 侧脚本（如 `xtark/scripts/android_remote.bat`）默认 `XTARK_HOST=192.168.1.169`，**不会**连到 VM。

---

## 6. 其他 home 目录

| 路径 | 说明 |
|------|------|
| `~/Desktop` | 空（无快捷方式） |
| `~/Softwares` | 空目录，厂商预留 |
| `~/Documents` 等 | 标准 Ubuntu 用户目录 |

系统级塔克脚本仅 `/usr/share/xtark/xtark_vmwareStartup.sh`（登录横幅 + 网段检查）。

---

## 7. 典型工作流

1. 真机 `169` 上电，确认 `ping 192.168.1.169` 通。
2. SSH 登录 VM `154`，确认 `ROS Master URI` 指向 `169`。
3. 在**真机**手动启动 `pc_stack`（与 `android_stack` / `qt_stack` 互斥）：

```bash
# 真机（首次部署脚本：xtark\scripts\pc_stack_remote.bat deploy）
~/ros_ws/scripts/pc_stack.sh camera-start
# 或 full-start / radar2d-start
~/ros_ws/scripts/pc_stack.sh full-status
```

4. 在 **VM** 运行 `vmware/qt`（纯客户端，本地 RViz，不 SSH）：

```bash
cd ~/ros-dev/vmware/qt && ./run.sh
```

Windows 侧：

```bat
rem 一次性：仅 VM Qt 客户端
vmware\scripts\vm_qt_remote.bat bootstrap

rem 日常：小车手动 pc_stack 后
vmware\scripts\vm_qt_remote.bat run
```

`pc_stack camera-check` / `full-check` 验证深度 topic。Qt 内用「检查环境」做 `rostopic list`。

手动 RViz（无 Qt 时）：

```bash
# VM 终端
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
export ROS_MASTER_URI=http://192.168.1.169:11311
export ROS_IP=192.168.1.154
rviz -d ~/ros-dev/vmware/qt/config/rviz_depth_light.rviz
```

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| 横幅提示「不在同一网段」 | 检查 VM 网卡 `ens33` 是否与机器人同 `192.168.1.x`；改 VMware 桥接/NAT |
| RViz 无 `/scan` | 真机未启驱动或 Master 未起；先在 169 上 `rostopic list` |
| VM 找不到 `xtark_nav` | 正常——该包只在真机；VM 仅 ctl + viz |
| `LIBGL_ALWAYS_SOFTWARE=1` | VMware 默认软件 GL；RViz 可能较慢，属预期 |
| 想从 Windows 部署真机 pc_stack | `xtark/scripts/pc_stack_remote.bat deploy`（目标 **169**） |
| 想从 Windows 部署 VM Qt 客户端 | `vmware/scripts/vm_qt_remote.bat bootstrap` 或 `deploy` |
| 想从 Windows 部署真机代码 | 目标 host 仍是 **169**，见 `xtark/scripts/android_remote.bat`、`qt_remote.bat` |

---

## 9. 维护说明

- 探测日期：**2026-07-03**；IP 以局域网 DHCP 为准，变化时改 VM `~/.bashrc` 中 `ROBOT_IP`。
- 本文描述的是**厂商出厂 VM 布局**；若后续在 VM 上自行扩充 `ros_ws`，需同步更新本文第 4、5 节。
- 密码、密钥勿写入 Git；自动化请配置 SSH 公钥（步骤同 [xtark/docs/远端登录.md](../../xtark/docs/远端登录.md) §2.1，host 换为 `192.168.1.154`）。
