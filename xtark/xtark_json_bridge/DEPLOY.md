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
python send_cmd_vel_json.py --host 192.168.1.169 --linear-x 0.10 --duration 2
```

停止：

```bash
python send_cmd_vel_json.py --host 192.168.1.169
```

## 5. 安全要求

- 第一轮测试必须架空轮子或留足空间。
- `linear_x` 建议不超过 `0.10`。
- `angular_z` 建议不超过 `0.20`。
- 适配节点默认 0.5 秒收不到控制指令就发布停止。
