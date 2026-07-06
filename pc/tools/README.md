# PC JSON 工具

这些脚本运行在 PC / RK3568 / 开发机上，不依赖 ROS，不部署到 xtark Nano。

前提：xtark 上已经启动 `xtark_driver` 和 `xtark_json_bridge`。

## 低速指令测试

```bash
python send_cmd_vel_json.py --host 192.168.1.168 --linear-x 0.10 --duration 2
```

## 链路检查

检查 WSL2 / PC 到 xtark JSON 和 RK3568 的基础网络：

```bash
python check_links.py
```

## 键盘遥控

```bash
python xtark_json_keyboard.py --host 192.168.1.168 --port 8765 --speed 0.10 --turn 0.20
```

只遥控、不打印反馈：

```bash
python xtark_json_keyboard.py --host 192.168.1.168 --port 8765 --speed 0.10 --turn 0.20 --no-feedback
```

## 目录边界

```text
xtark/xtark_json_bridge/  车端 ROS1 JSON 适配包
pc/tools/                 PC / RK3568 外部命令行调试工具
pc/qt_client/             PC Qt 图形调试台
```
