# xtark_laser_odometry

**实验模块，不是主线里程计。**

```text
/scan -> rf2o_laser_odometry -> /odom_laser
```

- 默认只发布 `/odom_laser`。
- **不替换** `/odom`（轮子里程计主线照旧）。
- **不修改** gmapping、move_base、Android、Qt。
- **不发布**主链路 `odom -> base_footprint` TF（`publish_tf:=false`）。

阶段一只做旁路验证，对比 `/odom_laser` 与 `/odom`。

## 依赖

机器人端（ROS Melodic）需要已安装 `rf2o_laser_odometry`：

```bash
rospack find rf2o_laser_odometry
```

若未安装，可先试 apt（以实机为准）：

```bash
sudo apt install ros-melodic-rf2o-laser-odometry
```

apt 不可用时再考虑源码安装到工作空间，**不要把 rf2o 源码混进本仓库主线**。

参数名以实机 `rf2o_laser_odometry` 版本为准；本包 launch 已按上游示例使用：

- `laser_scan_topic`
- `odom_topic`
- `base_frame_id`
- `odom_frame_id`
- `publish_tf`
- `init_pose_from_topic`（必须为空字符串，否则节点会一直 Waiting for laser_scans）
- `freq`
- `verbose`

## 部署

将本包放到机器人工作空间：

```text
~/ros_ws/src/xtark_laser_odometry
```

编译：

```bash
cd ~/ros_ws
catkin_make
source devel/setup.bash
```

前提：主线 bringup 已运行，`/scan` 与 `/odom` 正常（例如 `robot_stack.sh start` 或 `android_stack.sh start`）。

## 启动

```bash
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
roslaunch xtark_laser_odometry rf2o_odom_laser.launch
```

或使用轻量脚本（不并入 `robot_stack.sh` / `android_stack.sh`）：

```bash
~/ros_ws/scripts/laser_odom_experiment.sh start
```

**Qt 遥控 + 三路对照 + rosbag**：

```bash
robot_stack.sh stop                    # 手动停其它栈
laser_odom_compare_stack.sh start
laser_odom_compare_stack.sh record
laser_odom_compare_stack.sh stop
robot_stack.sh start
```

`compare_stack` 的 `record` 含 `/cmd_vel`、`/odom_raw`、`/odom`、`/imu`、
`/odom_laser`、`/scan`、`/tf_static` 以及四轮 `set/vel` 反馈。各脚本互不调用。

## 验证

```bash
rostopic hz /scan
rostopic hz /odom
rostopic hz /odom_laser
rostopic echo /odom_laser -n 1
```

记录对比 bag：

```bash
rosbag record /scan /odom /odom_laser
```

手动低速控车时同时观察 `/odom` 与 `/odom_laser`：

| 动作 | 期望 |
|------|------|
| 前进 | `/odom_laser` 的 x 有合理变化 |
| 原地转 | yaw 有合理变化 |
| 静止 | 不明显持续漂移 |

生成文字报告与自包含 HTML/SVG 图表（无需 Matplotlib/Plotly）：

```bash
python2 ~/ros_ws/tools/analyze_laser_odom_bag.py <bag> \
  --report ~/xtark_logs/laser_odom_compare/analysis.txt \
  --html-report ~/xtark_logs/laser_odom_compare/analysis.html
```

HTML 包含 SE(2) 对齐轨迹、前进/横移/旋转速度、yaw、一致性误差和四轮
目标/反馈曲线。`/cmd_vel` 只表示控制意图；没有外部真值时，图中的误差只能称为
不同估计器之间的“一致性误差”。

## 停止

```bash
# Ctrl+C 结束 roslaunch，或：
~/ros_ws/scripts/laser_odom_experiment.sh stop
```

## 禁止事项

- 不要把 `/odom_laser` remap 成 `/odom`。
- 不要默认 `publish_tf:=true` 且 `odom_frame_id:=odom`（会与主线 TF 冲突）。
- 不要据此宣称「已替代轮子里程计」。

详细实验步骤见 `xtark/docs/激光里程计实验方案.md`。
