# cmd_vel → car_web HTTP 对接方案

Jetson `~/qt/car_web/main.py` 已经在 8080 上跑着（stdlib `HTTPServer`，直接驱动
COM 电机）。当前 `cmd_vel_car_web_bridge` 只做 dry-run，打印
`CONTROL_ACTION=…` 后回显 `/vehicle/control_action`，不发 HTTP、不动车。

本文档规划把 bridge 从 dry-run 升级为「可选调用 car_web」的实现路径，分三步。
每一步都可以停在原地。

## 目标链路

```text
VMware cockpit
  -> ROS2 /cmd_vel                                      (已通)
Jetson ~/qt/ros2_ws
  -> cmd_vel_car_web_bridge
     -> /vehicle/control_action (回显)                 (已通)
     -> HTTP GET 127.0.0.1:8080/api/...  (新增, 可关)
Jetson ~/qt/car_web
  -> COM 电机 / 舵机 / 升降 / 扒手                     (真机)
```

## 现有事实

- `main.py` 是标准库 `HTTPServer`，端口 `0.0.0.0:8080`，pid 常驻。
- 已确认存在的路由（`path.startswith` 分派，非 Flask）：
  - `GET /api/rear_drive?dr=<int>&sp=<int>` → `rear_drive(dr, sp)`
  - `GET /api/rear_stop` → `rear_stop()`
  - `GET /api/motor_run?...` → `motor_run(mid, sp, dr)`
  - `GET /api/steer_motor_run?...` → `steer_motor_run(mid, sp, dr)`
  - 另有 `/api/grab/*`（前扒手）、`/api/lift/*`（升降）、`/api/level/*`（调平），
    本阶段不用。
- car_web 与 bridge 在同一台 Jetson，走 `127.0.0.1:8080`，无跨机延迟。

## 未确认（Step 1 要读源码定死）

1. `rear_drive(dr, sp)` 中 `dr` 的方向枚举：`1=前进 / 0=后退` 还是相反？
2. `sp` 单位与合法范围（PWM? RPM? 0–100? 0–255?）。
3. 「左右转」实现方式：
   - 单舵机 `steer_motor_run` 打角度 + 后驱同时走？
   - 还是差速？（当前底盘是 rwd 后驱，看起来更像「后驱 + 前舵机」阿克曼车）
4. 停车语义：`rear_stop()` 是否也停舵机、是否清零角度。
5. HTTP 单发耗时：以 10Hz 的 `/cmd_vel` 重发频率，是否会打爆 stdlib
   `HTTPServer`（同步单线程，需要评估）。

## Step 1（明天先做，只读，零风险）

1. `bash jetson/scripts/jetson.sh pull car_web`
   - 只读同步远端 `~/qt/car_web` → `jetson/mirror/car_web/`
   - 已在 `jetson/README.md` 明确：car_web 只是同事版本的镜像，我们不改。
2. 读源码定死上面 5 个未确认项，产出一张映射表：

   | ROS2 CONTROL_ACTION | car_web HTTP 调用 | 备注 |
   |---|---|---|
   | FORWARD | `GET /api/rear_drive?dr=?&sp=?` | dr / sp 待定 |
   | BACKWARD | `GET /api/rear_drive?dr=?&sp=?` | 反向 |
   | TURN_LEFT | `GET /api/steer_motor_run?...` (+ `rear_drive`?) | 待定 |
   | TURN_RIGHT | `GET /api/steer_motor_run?...` (+ `rear_drive`?) | 待定 |
   | STOP | `GET /api/rear_stop` (+ 舵机复位?) | 待定 |

3. 把映射表回写到本文档，覆盖「未确认」章节。

**Step 1 完成的判定**：文档里映射表全部填实，没有「待定」。

## Step 2（Step 1 定死后做，风险可控）

给 `cmd_vel_car_web_bridge` 加两个 ROS2 参数：

- `enable_car_web`（`bool`，默认 `False`）
- `car_web_base_url`（`string`，默认 `http://127.0.0.1:8080`）

行为：

- `enable_car_web=False`：跟今天完全一样，只 log + 回显，不发 HTTP。
- `enable_car_web=True`：在 log 之后追加一次 `http.client` GET；请求异常只
  `get_logger().warning(...)`，不 crash 节点。
- 节流：**动作切换时才发一次**，同动作连续到达不重复发（避免 10Hz 打爆
  HTTPServer）。STOP 有 500ms 保底心跳，防止 car_web 侧漏掉停车。

`bridge_stack.sh` 也要跟着补一个开关（例如 `BRIDGE_ENABLE_CAR_WEB=1`），
默认关。

**Step 2 完成的判定**：`enable_car_web=False` 跑一整天，日志跟今天一模一样，
无新增 warning；`enable_car_web=True` 但车不通电时，日志里能看到 HTTP 请求
被打出，car_web 侧能收到但硬件因不通电而 no-op。

## Step 3（真机，必须现场看着做）

前置：车轮离地（用垫木顶起），STOP 键在手。

1. Jetson 端手工起 bridge：
   ```bash
   bash jetson/scripts/jetson.sh ros2 stop
   BRIDGE_ENABLE_CAR_WEB=1 bash jetson/scripts/jetson.sh ros2 start
   ```
2. cockpit 端**先按 STOP，再按 FORWARD 一下就松**（≤ 200ms）。
   观察 rwd 电机是否响应、方向是否正确。
3. 依次测 BACKWARD、TURN_LEFT、TURN_RIGHT，每次都先短促、再长按。
4. 任何一步不对 → 立刻 `ros2 stop` + `curl /api/rear_stop`。

**Step 3 完成的判定**：5 个动作在离地状态下方向、速度、停车都对得上；
STOP 能可靠切断电机。落地测试**不在本阶段**。

## 边界（本方案不做的事）

- 不改 car_web（`main.py` / `model/*` 一根手指都不动）。
- 不接前扒手、升降、调平、tilt 等 API。
- 不做导航、SLAM。
- 不改 `/cmd_vel` topic 名或语义。
- 不做「持续按住 = 持续 HTTP」，一律走「动作切换才发」+ STOP 心跳。

## Open questions（做之前需要你拍板一次）

1. Step 2 的 ROS2 参数默认值：`enable_car_web=False` 我倾向默认关，你同意吗？
2. 转向如果最终是「舵机 + 后驱同时」的组合，`TURN_LEFT/RIGHT` 时后驱要不要给一个
   低速前进（比如 sp=20）？还是原地打舵？
3. Step 3 现场测试你自己在跟前，还是我给你一份 checklist 你独立跑？
