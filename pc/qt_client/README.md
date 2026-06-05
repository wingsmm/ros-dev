# xtark 底盘 JSON 调试台

PC 端 PyQt5 小工具，用于第二阶段联调：连接、手动控制、状态显示、日志、安全停车。

不依赖 ROS，不依赖 xtark 环境。

## 依赖

```bash
pip install -r requirements.txt
```

使用 PyQt5 最后维护版本 `5.15.11`。

## 启动

建议在 **PowerShell / CMD** 用 venv 里的 Python 启动（Git Bash 下 PyQt5 可能 segfault）：

```powershell
cd pc/qt_client
.\.venv\Scripts\Activate.ps1
python app.py
```

## 前置条件

xtark 上先运行：

```bash
roslaunch xtark_driver xtark_bringup.launch
roslaunch xtark_json_bridge json_base_adapter.launch
```

## 功能

| 优先级 | 功能 |
|--------|------|
| P0 | 连接 / 断开 TCP `host:port` |
| P0 | 按钮 + 键盘 `WASD/IJKL` 发 `cmd_vel` |
| P0 | 停车按钮，`K` / 空格，退出/断开前发 0 |
| P0 | `odom_base`、`base_status` 实时显示 |
| P1 | 线速度 / 角速度参数 |
| P1 | JSON 收发日志 |
| P1 | 控制权状态（控制中 / 空闲 / 失联） |
| P2 | `QSettings` 保存 host/port/速度 |

## 键盘

| 键 | 动作 |
|----|------|
| W / I / ↑ | 前进 |
| S / ↓ | 后退 |
| A / J | 左转 |
| D / L | 右转 |
| Q | 左移 |
| E | 右移 |
| K / 空格 | 停车 |

按住才持续运动（10 Hz 发送），适配 bridge `cmd_timeout_sec=0.5`。

## 目录

```text
qt_client/
├─ app.py
├─ json_client.py
├─ widgets/
│  ├─ control_panel.py
│  ├─ status_panel.py
│  └─ log_panel.py
└─ README.md
```
