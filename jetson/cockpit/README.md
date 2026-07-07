# cockpit — PC/WSL 上位机开发端

跑在 PC (WSL) 上，连接 Jetson 82 做**控制 + 观测 + 算法集成**。跟 `jetson/mirror/` 是完全不同的东西：

| | `jetson/mirror/` | `jetson/cockpit/` |
|---|---|---|
| 跑在哪 | 远端 Jetson (`~/qt/`)，本地是镜像 | 本地 PC / WSL |
| 部署 | 双向 rsync 同步（`jetson.sh pull/push`） | 不部署到远端；就地跑 |
| 干什么 | 车端服务（`car_web` Flask、`ros2_ws` ROS2 栈） | 上位机：发指令、看状态、跑算法、可视化 |
| 谁改动 | 两边都可能改 | 只在本地改 |

## 职责边界（做什么）

- 通过 **ssh** 触发远端命令、抓 log、探状态（走 `jetson/scripts/jetson.sh`）
- 通过 **HTTP** 调远端 `car_web` 的 Flask 接口发控制指令
- 通过 **ROS2 DDS** 订 Jetson 上的 topic（若同网段，`ROS_DOMAIN_ID` 对齐即可，PC 不需要跟远端 ROS Master 走 ROS1 那套）
- 本地跑视觉 / 规划 / 决策算法，把结果通过 HTTP 或 ROS2 topic 推到 Jetson
- 可选：Web 前端 / PyQt GUI / 纯 CLI，看后面决定

## 不做什么

- 不部署自己到 Jetson。cockpit 的代码就在 PC 上跑，不 rsync 到远端。
- 不管理远端进程的生命周期（那是 `jetson/mirror/car_web` 或 `ros2_ws` 自己的事）。
- 不做行尾/编码转换、双向同步、构建部署 —— 这些都是 `jetson/scripts/jetson.sh` 的职责。

## 目录约定（暂定）

```text
cockpit/
  README.md
  requirements.txt      Python 依赖
  .env                  cockpit 自己的运行时配置（gitignore，非 jetson/.env；不留示例）
  src/
    cockpit/            Python 包，import cockpit.xxx
      __init__.py
      config.py         读 .env
      remote/           跟 Jetson 通信的适配层
        ssh_client.py   薄封装（如果需要脱开 jetson.sh 直接调 ssh）
        car_web_api.py  car_web Flask HTTP client
        ros2_bridge.py  可选：rclpy 直连
      control/          控制层
      algo/             算法层
      ui/               可选：CLI / Web / Qt 入口
    main.py             或按 ui/ 入口分多个
  scripts/
    dev.sh              本地起 venv、装依赖、跑 lint
    run.sh              本地起主进程
  tests/
```

## 与远端的对接点（待落实）

| 通道 | 远端端点 | 目的 | 状态 |
|---|---|---|---|
| ssh | `jetson.sh <cmd>` | 探测、抓 log | 已通 |
| HTTP | `car_web` Flask（端口待确认，默认 5000？） | 发运动指令、读传感器状态 | **未确认** |
| ROS2 topic | `/xxx`（待远端 ros2_ws 起来） | 订 SLAM/odom/scan | **未启用** |

需要下一步确认：

1. `car_web` 现在实际暴露在哪个端口？路由约定？
2. `ros2_ws` 里 `my_motor_ctrl` 发布/订阅哪些 topic？
3. cockpit 第一个功能是「HTTP 遥控 car_web」还是「订 ROS2 topic 做算法」？

## 开发

```bash
cd jetson/cockpit
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` 目前只有最小集，后面按需加。
