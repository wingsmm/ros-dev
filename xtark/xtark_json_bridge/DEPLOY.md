# xtark_json_bridge 部署测试说明

## 1. 复制到 xtark

目标路径：

```text
~/ros_ws/src/xtark_json_bridge
```

## 2. 编译

```bash
cd ~/ros_ws
catkin_make
source devel/setup.bash
```

## 3. 启动

先启动 xtark 原生底盘：

```bash
roslaunch xtark_driver xtark_bringup.launch
```

再启动 JSON 适配：

```bash
roslaunch xtark_json_bridge json_base_adapter.launch
```

默认监听：

```text
0.0.0.0:8765
```

## 4. 低速验证

从 PC 发送低速前进 2 秒：

```bash
cd pc/tools
python send_cmd_vel_json.py --host 192.168.1.169 --linear-x 0.10 --duration 2
```

停止：

```bash
cd pc/tools
python send_cmd_vel_json.py --host 192.168.1.169
```

## 5. 键盘遥控验证

xtark 上保持 `xtark_driver` 和 `json_base_adapter` 运行。

PC 或 RK3568 上：

```bash
cd pc/tools
python xtark_json_keyboard.py --host 192.168.1.169 --port 8765 --speed 0.15 --turn 0.4
```

按键逻辑与远端 `xtark_twist_keyboard.py` 相同；建图时建议低速，按住移动键可连续发送。默认会打印低频 `odom_base` / `base_status` 反馈。

如果只想遥控，不想刷反馈：

```bash
cd pc/tools
python xtark_json_keyboard.py --host 192.168.1.169 --port 8765 --speed 0.15 --turn 0.4 --no-feedback
```

## 6. 安全要求

- 第一轮测试必须架空轮子或留足空间。
- `linear_x` 建议不超过 `0.10`。
- `angular_z` 建议不超过 `0.20`。
- 适配节点默认 0.5 秒收不到控制指令就发布停止。

## 7. 第一阶段结论

2026-06-05 已完成第一阶段低速验证：

| 项目 | 结果 |
|------|------|
| PC 键盘通过 JSON 控制 xtark | 通过 |
| xtark 回传 `odom_base` | 通过 |
| xtark 回传 `base_status` | 通过 |
| 不改 `xtark_driver` / 底盘串口 | 满足 |

下一阶段先做稳定化和联调，不急于进入自主导航闭环。
