# VMware Qt 客户端整体方案

本文面向后续实施 agent / 苦力使用。当前架构已明确：**`pc_stack` 是小车 169 上专门服务 VMware Qt 的机器人侧服务栈；`vmware/qt` 是 VMware 154 上的纯客户端 GUI。**

不要把 `qt_stack`、`pc/qt_client`、`pc_stack` 混在一起：

- `pc/qt_client`：PC / WSL 侧旧 Qt 客户端路径。
- `qt_stack`：对应 PC / WSL Qt 客户端的机器人侧栈，不是本方案主线。
- `pc_stack`：对应 VMware Qt 客户端的机器人侧栈，部署并运行在小车 `192.168.1.169`。
- `vmware/qt`：运行在 VMware `192.168.1.154`，只负责连接、检查、RViz 配置与显示。

## 一句话结论

小车上手动启动 `pc_stack xxx-start`，VMware 上直接运行 `vmware/qt/run.sh`。VMware Qt 不需要 SSH，不需要远程启动脚本，不需要本地 `pc_stack.sh`，只需要本地 ROS1 环境、RViz 和正确的 `ROS_MASTER_URI` / `ROS_IP`。

## 背景

现有 `pc/qt_client` 因深度相机链路和显示路径较长，出现明显卡顿。官方 VMware 环境本身就是 ROS1 Melodic + RViz 的开发终端，适合直接连接小车 ROS Master 并用 RViz 订阅 `/camera/depth/image_raw`。

本方案的目标不是复制 `pc/qt_client`，而是用 VMware Qt 做一个“纯 ROS1/RViz 客户端控制台”：

- 小车负责启动真实机器人服务。
- VM 负责连接 ROS Master、检查 topic、打开 RViz。
- 深度相机优先走 ROS1 topic + RViz Image Display，不绕 Windows / WSL / HTTP / ROS2 Bridge。

## 正确分工

```text
小车 192.168.1.169
  ├─ 部署 ~/ros_ws/scripts/pc_stack.sh
  ├─ 手动执行 pc_stack camera-start / radar2d-start / full-start / stop / status
  ├─ 启动 roscore / bringup / 相机 / 深度相机 / 雷达 / 里程计等机器人侧服务
  └─ 发布 /scan /odom /camera/image_raw /camera/depth/image_raw 等 ROS1 topic

VMware 192.168.1.154
  ├─ 运行 vmware/qt
  ├─ source /opt/ros/melodic/setup.bash 和 ~/ros_ws/devel/setup.bash
  ├─ export ROS_MASTER_URI=http://192.168.1.169:11311
  ├─ export ROS_IP=192.168.1.154
  ├─ 本地执行 rostopic list/info/echo/hz 做诊断
  └─ 本地执行 rviz -d config/*.rviz 打开不同显示配置
```

## 明确不要做

实施 agent 必须遵守：

- 不要在 VMware Qt 里 SSH 到小车。
- 不要在 VMware Qt 里远程执行小车脚本。
- 不要要求 VM 本地存在 `~/ros_ws/scripts/pc_stack.sh`。
- 不要用 `pc_stack_remote.bat deploy` 给 **VM** 部署 `pc_stack`（该脚本只面向真机 169）。
- 不要把 `pc_stack` 当成 VM 侧 RViz 启停脚本。
- 不要把 `qt_stack` 写进本方案主流程。
- 不要复制 `pc/qt_client` 的 ROS2 / JSON / HTTP 架构。
- 不要在第一版做 Qt 内置 `/cmd_vel` 控车。
- 不要把“界面能打开”当成“深度相机不卡顿已验证”。

## 目标

1. 在 `vmware/qt` 下实现一个可启动的 PyQt5 客户端。
2. 客户端启动后能自动/手动检查 ROS 环境：
   - ROS Master：`http://192.168.1.169:11311`
   - ROS IP：VM 本机 IP，例如 `192.168.1.154`
   - ROS setup 是否存在
   - RViz 是否可执行
3. 客户端能检查关键 topic：
   - `/scan`
   - `/odom`
   - `/camera/image_raw`
   - `/camera/depth/image_raw`
   - `/camera/depth/camera_info`
4. 客户端能一键打开本地 RViz，并使用不同配置：
   - 激光/地图基础视图
   - 深度轻量视图
   - RGB + Depth 诊断视图
5. 客户端能停止自己启动的 RViz。
6. 客户端能执行深度诊断：
   - publisher 是否存在
   - 是否能收到 1 帧
   - `rostopic hz` 短采样
7. 优先验证：VMware + ROS1 RViz 直连深度 topic 是否能解决或显著缓解卡顿。

## 小车侧 pc_stack 要求

`pc_stack.sh` 部署在小车 `192.168.1.169` 的 `~/ros_ws/scripts/` 下。它是 VMware Qt 的机器人侧服务栈，不是 VM 客户端脚本。

建议支持这些命令：

```bash
~/ros_ws/scripts/pc_stack.sh camera-start
~/ros_ws/scripts/pc_stack.sh camera-stop
~/ros_ws/scripts/pc_stack.sh camera-status
~/ros_ws/scripts/pc_stack.sh camera-check

~/ros_ws/scripts/pc_stack.sh radar2d-start
~/ros_ws/scripts/pc_stack.sh radar2d-stop
~/ros_ws/scripts/pc_stack.sh radar2d-status
~/ros_ws/scripts/pc_stack.sh radar2d-check

~/ros_ws/scripts/pc_stack.sh full-start
~/ros_ws/scripts/pc_stack.sh full-stop
~/ros_ws/scripts/pc_stack.sh full-status
~/ros_ws/scripts/pc_stack.sh full-check
```

如果现有 `pc_stack.sh` 命令名不同，实施 agent 应统一为上述语义，或在 README 中写清楚映射关系。

### `camera-start` 至少启动

- `roscore`
- 底盘/基础 bringup，如相机依赖 TF 或基础驱动
- RGB 相机 topic：`/camera/image_raw`
- 深度相机 topic：`/camera/depth/image_raw`
- 深度相机信息：`/camera/depth/camera_info`

### `radar2d-start` 至少启动

- `roscore`
- 底盘/雷达 bringup
- `/scan`
- `/odom`
- `/odom_raw` 如已有

### `full-start` 至少启动

- `radar2d-start` 覆盖内容
- `camera-start` 覆盖内容
- 其他 VMware Qt 需要观察的基础 topic

## VMware Qt 推荐目录结构

```text
vmware/qt/
├── README.md
├── requirements.txt
├── run.sh
├── app.py
├── main_window.py
├── config/
│   ├── vmware_client.env.example
│   ├── rviz_mapping.rviz
│   ├── rviz_depth_light.rviz
│   └── rviz_rgb_depth_diag.rviz
├── core/
│   ├── env.py
│   ├── process_manager.py
│   ├── ros1_probe.py
│   └── rviz_commands.py
└── ui/
    ├── status_panel.py
    ├── rviz_panel.py
    └── topic_panel.py
```

不要新增 `stack_commands.py`。客户端只用 `rviz_commands.py` 启停本地 RViz。

## VMware Qt UI 设计

窗口采用单页控制台，不做复杂导航。

### 1. 顶部环境状态

显示：

- Robot IP：`192.168.1.169`
- VM ROS IP：自动检测或配置，例如 `192.168.1.154`
- ROS Master：`http://192.168.1.169:11311`
- Master 可达 / 不可达
- RViz 状态：未启动 / 运行中 / 已停止

按钮：

- `刷新状态`
- `检查环境`

`检查环境` 应本地执行：

```bash
rostopic list
```

并输出明确结果。不要调用任何 `pc_stack.sh`。

### 2. RViz 配置区

单选：

- `激光/地图`
- `深度轻量`
- `RGB+Depth 诊断`

按钮：

- `启动 RViz`
- `停止 RViz`

启动时本地执行：

```bash
rviz -d <selected-rviz-config>
```

必须只管理自己启动的 RViz 进程。不要 `pkill rviz` 杀用户手动开的 RViz，除非 README 明确说明且 UI 有确认。

### 3. Topic 诊断区

按钮：

- `检查关键 topic`
- `深度诊断`

关键 topic 检查：

```bash
rostopic info /scan
rostopic info /odom
rostopic info /camera/image_raw
rostopic info /camera/depth/image_raw
rostopic info /camera/depth/camera_info
```

深度诊断：

```bash
rostopic info /camera/depth/image_raw
timeout 12 rostopic echo /camera/depth/image_raw -n 1
timeout 6 rostopic hz /camera/depth/image_raw
rostopic info /camera/depth/camera_info
```

UI 显示：

- publisher 是否存在
- 是否收到一帧
- hz 采样输出
- 明确错误文本

## RViz 配置策略

应提供三份 RViz 配置，不依赖厂商默认配置。

### `rviz_mapping.rviz`

用途：基础激光/地图。

Display：

- Grid
- TF
- LaserScan：`/scan`
- Odometry：`/odom`
- Map：`/map`，没有 publisher 时不影响启动

### `rviz_depth_light.rviz`

用途：深度相机不卡顿验收首选。

Display：

- Image：`/camera/depth/image_raw`
- RGB Image 可默认关闭
- TF 可默认关闭

要求：

- 不默认启用 PointCloud / DepthCloud。
- Queue Size 设置为 1 或 2。
- Fixed Frame 默认 `base_link` 或 `base_footprint`；若现场 TF 不全，README 写明可切到相机 frame。

### `rviz_rgb_depth_diag.rviz`

用途：RGB + Depth 同时诊断。

Display：

- Image：`/camera/image_raw`
- Image：`/camera/depth/image_raw`
- TF
- LaserScan 可选，默认关闭

## ROS 环境加载

VMware Qt 的所有本地 ROS/RViz 子进程必须带上：

```bash
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
export ROS_MASTER_URI=http://192.168.1.169:11311
export ROS_IP=<VM 本机 IP>
export LIBGL_ALWAYS_SOFTWARE=1
```

`ROS_IP` 检测：

1. 优先读配置文件 `config/vmware_client.env`。
2. 再读环境变量 `ROS_IP`。
3. 再通过 `ip route get 192.168.1.169` 找 VM 到小车的网卡。
4. 再通过 `ip -4 addr show <iface>` 获取 VM IP。
5. 检测失败时提示用户手动设置。

配置示例：

```dotenv
ROBOT_IP=192.168.1.169
ROS_MASTER_URI=http://192.168.1.169:11311
ROS_IP=192.168.1.154
ROS_SETUP=/opt/ros/melodic/setup.bash
WS_SETUP=/home/xtark/ros_ws/devel/setup.bash
LIBGL_ALWAYS_SOFTWARE=1
```

## 实现步骤

### 第 1 阶段：去掉 VM 本地 pc_stack 依赖

如果当前 `vmware/qt` 已经实现了本地 `pc_stack.sh` 调用，必须修改：

1. 删除“pc_stack 脚本存在性”检查。
2. 删除在 Qt 内提示部署 `pc_stack` 到 VM 的文案。
3. 删除 `pc_stack status/check/viz-start/viz-stop/stop` 调用。
4. 使用 `rviz_commands.py` 只负责本地 RViz：

```bash
rviz -d <config>
rostopic list
rostopic info ...
rostopic echo ...
rostopic hz ...
```

验收：

- VM 本地不存在 `~/ros_ws/scripts/pc_stack.sh` 时，Qt 仍可启动。
- `检查环境` 不再提示部署 `pc_stack` 到 VM。
- `启动 RViz` 直接启动本地 RViz。

### 第 2 阶段：环境检查

实现：

- ROS setup 路径检查
- workspace setup 路径检查
- ROS Master 可达检查
- VM ROS IP 显示
- RViz 可执行检查

本地命令：

```bash
rostopic list
which rviz
```

验收：

- 小车未启动 `pc_stack` 时，显示 Master 不可达或 topic 缺失。
- 小车启动 `pc_stack camera-start` 后，Master 可达。

### 第 3 阶段：RViz 启停

实现：

- UI 选择 RViz 配置。
- 本地 `rviz -d <config>` 启动。
- 用 `QProcess` 或等价进程管理保存 RViz 进程句柄。
- 停止按钮只停止该句柄对应的 RViz。

验收：

- 点击 `深度轻量` + `启动 RViz`，打开深度配置。
- 点击 `RGB+Depth 诊断` + `启动 RViz`，打开诊断配置。
- `停止 RViz` 不误杀其他 RViz。

### 第 4 阶段：topic 诊断

实现：

- `检查关键 topic`
- `深度诊断`
- 所有耗时命令必须异步执行，不阻塞 UI。
- 超时后能中止命令并恢复 UI。
- 后台线程不得直接更新 Qt widget，只能通过 signal 回到主线程。

验收：

- `/camera/depth/image_raw` 无 publisher 时显示清楚。
- 有 publisher 但无帧时显示清楚。
- 有帧时显示 `[OK] 收到 1 帧深度图` 和 hz 输出。

### 第 5 阶段：README 和操作流

`vmware/qt/README.md` 必须写清楚：

```bash
# 小车 169，手动启动 VMware Qt 对应服务
~/ros_ws/scripts/pc_stack.sh camera-start

# VM 154，启动纯客户端
cd ~/ros-dev/vmware/qt
./run.sh
```

并强调：

- VMware Qt 不 SSH 到小车。
- VMware Qt 不启动小车服务。
- VMware Qt 不依赖 VM 本地 `pc_stack.sh`。
- 小车侧 `pc_stack` 与 PC/WSL 的 `qt_stack` 不要混用。

## 深度相机卡顿验证方案

现场验证按这个顺序：

1. 小车启动：

```bash
~/ros_ws/scripts/pc_stack.sh camera-start
```

2. VM 启动：

```bash
cd ~/ros-dev/vmware/qt
./run.sh
```

3. Qt 内点击：

```text
检查环境
检查关键 topic
深度诊断
选择「深度轻量」
启动 RViz
```

4. 观察 3-5 分钟：

- 深度图是否连续刷新
- RViz 是否卡顿
- `rostopic hz /camera/depth/image_raw` 是否稳定
- CPU 占用是否异常

判断：

- VM + `rviz_depth_light.rviz` 流畅：说明 PC/WSL Qt 链路大概率是卡顿主因。
- VM 也卡：优先排查小车相机驱动、USB、topic 发布频率、VMware 软件渲染。
- 只开 PointCloud/DepthCloud 才卡：默认配置不得启用点云。

## 风险与注意事项

- VMware 下 `LIBGL_ALWAYS_SOFTWARE=1` 可能导致复杂 RViz 显示慢；深度验收默认只显示 Image。
- 深度图格式可能是 `16UC1`，RViz Image Display 的 min/max、normalize 可能需要现场调整。
- `ROS_MASTER_URI` 必须指向小车 `192.168.1.169`，不是 VM。
- `ROS_IP` 必须是 VM 自己的 IP，不能误设成小车 IP。
- 小车侧 `pc_stack` 必须先启动，否则 VM 只能显示 Master 不可达或 topic 缺失。
- 不写密码、token、私钥。
- 当前阶段不做真实遥控按钮，避免把显示验收和运动风险绑在一起。

## 需要修改的文件

### 必改

- `vmware/qt/README.md`
  - 改成“小车手动启动 pc_stack，VM 运行纯客户端”。
  - 删除「VM 本地 pc_stack」相关说明。

- `vmware/qt/core/env.py`
  - 保留 ROS 环境、IP、setup 检查。
  - 删除 VM 本地 `PC_STACK_SCRIPT` 作为必需项。

- `vmware/qt/core/rviz_commands.py`
  - 删除或改名为 `rviz_commands.py`。
  - 不再调用 `pc_stack.sh`。

- `vmware/qt/main_window.py`
  - 删除 `_require_stack()`。
  - `检查环境` 改为本地 ROS 检查。
  - `启动 RViz` 改为本地 `rviz -d`。
  - `停止 RViz` 只停止自身启动的 RViz。

- `vmware/qt/ui/status_panel.py`
  - 文案从 `pc_stack` 状态改为 `ROS Master / RViz` 状态。

- `vmware/qt/ui/rviz_panel.py`
  - 文案删除“仅 viz / pc_stack”。

### 保留

- `vmware/qt/config/rviz_mapping.rviz`
- `vmware/qt/config/rviz_depth_light.rviz`
- `vmware/qt/config/rviz_rgb_depth_diag.rviz`
- `vmware/qt/core/ros1_probe.py`
- `vmware/qt/core/process_manager.py`

### 小车侧

- `xtark/scripts/pc_stack.sh`
- `xtark/scripts/pc_stack_modules.sh`

这两个文件应代表“小车侧服务栈”，不要部署到 VM 作为客户端栈。若当前脚本注释或 README 写成 PC/VM client stack，应一并改正。

## 验收标准

### 代码验收

```bash
python3 -m py_compile app.py main_window.py core/*.py ui/*.py
```

要求：

- 无语法错误。
- 无跨线程 UI 更新。
- 耗时命令异步执行并带超时。

### VM 空环境验收

在 VM 上不部署 `pc_stack.sh`：

```bash
cd ~/ros-dev/vmware/qt
./run.sh
```

要求：

- Qt 能正常打开。
- 不提示在 VM 上部署 `pc_stack.sh`。
- 不要求 VM 本地存在 `~/ros_ws/scripts/pc_stack.sh`。
- 小车未启动时，环境检查给出 Master/topic 不可达提示。

### 小车服务验收

小车：

```bash
~/ros_ws/scripts/pc_stack.sh camera-start
```

VM Qt：

- `检查环境`：Master 可达。
- `检查关键 topic`：至少 `/camera/depth/image_raw` 有 publisher。
- `深度诊断`：能收到 1 帧，并有 hz 输出。
- `深度轻量` RViz 能显示深度图。

### 不要验收

本阶段不要要求：

- Qt 远程启动小车服务。
- Qt 内置控车。
- SSH 配置。
- JSON 网关。
- ROS2 / RViz2。

## 给实施 agent 的执行顺序

1. 先改文案和 README，统一概念：小车 `pc_stack`，VM `vmware/qt`。
2. 删除 VM 本地 `pc_stack` 依赖。
3. 确认 `rviz_commands.py` 只做本地 RViz。
4. 改 UI 按钮：只做本地环境检查、topic 诊断、RViz 启停。
5. 跑 `py_compile`。
6. 在 VM 上做空环境验收。
7. 小车手动启动 `pc_stack camera-start` 后做深度验收。

核心原则：**复杂度留在小车侧 `pc_stack`，VMware Qt 保持纯客户端。**
