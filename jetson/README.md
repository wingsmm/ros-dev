# jetson

Jetson 82 (`nvidia@172.0.0.82`) 相关的所有开发资产。三块：

```text
jetson/
  scripts/   与远端通信的入口（ssh / rsync）
  mirror/    远端 ~/qt/ 的同步区
  cockpit/   PC/WSL 上位机（永不部署到 Jetson）
```

## 关系图

```text
        [PC / WSL]                                [Jetson 82  ~/qt/]

        cockpit/  ── HTTP / ROS2 DDS ─────────►   car_web/   (副本, 来自同事)
           │                                      ros2_ws/   (自己写)
           │
        mirror/car_web/  ◄── pull ── rsync ────   car_web/
        mirror/ros2_ws/  ── push ── rsync ─────►  ros2_ws/
```

## 三个组件

| 目录 | 谁的代码 | 主开发在哪 | 同步方向 | 说明 |
|---|---|---|---|---|
| `scripts/jetson.sh` | 本仓库 | PC | — | connect / probe / pull / push / \<remote cmd\> |
| `mirror/car_web/` | 同事 Flask 副本 | 尽量对齐同事版本 | 双向（当前手工） | 相对同事仅端口 + `config/` 差异；不是 fork 分支 |
| `mirror/ros2_ws/` | 自己 | PC (WSL 里 ROS2 Humble) | 本地 → 远端 | WSL 写 → push → Jetson 编译运行 |
| `cockpit/` | 自己 | PC (WSL) | 无 | 控制 / SLAM / 算法；见 [cockpit/README.md](cockpit/README.md) |

## `.env`（不入库，不做示例）

| 文件 | 谁读它 | 内容 |
|---|---|---|
| `jetson/.env` | `scripts/jetson.sh`（ssh/rsync 用） | `HOST` `USER` `PORT` `PASSWORD` `KEY` |
| `cockpit/.env` | cockpit 应用运行时 | `CAR_WEB_BASE` `COCKPIT_ROS_DOMAIN_ID` 等 |

单人开发，不留 `.env.example`；缺 key 时按 `jetson.sh` / cockpit 代码里的报错提示补即可。两个 `.env` 都在 `jetson/.gitignore` 内。

## 常用命令

```bash
# 探远端环境（只读）
bash jetson/scripts/jetson.sh probe

# 双向同步
bash jetson/scripts/jetson.sh pull car_web        # 远端 ~/qt/car_web → 本地
bash jetson/scripts/jetson.sh push ros2_ws        # 本地 → 远端 (dry-run)
bash jetson/scripts/jetson.sh push ros2_ws --yes  # 真写；默认不带 --delete

# 交互式 ssh / 单条远端命令
bash jetson/scripts/jetson.sh
bash jetson/scripts/jetson.sh 'ros2 topic list'
```

## 行尾 / 编码规范

- 全部走 LF + UTF-8，`.bat` / `.ps1` 例外为 CRLF。
- 靠 `.gitattributes`（git 层）+ `.editorconfig`（编辑器层）双护栏。
- 远端源头本身可能带 CRLF/BOM（Windows 编辑的遗留），已一次性用 python 洗过一次；下次 `pull` 又脏就再洗，不折腾行尾自动化。

## 目录约束

- 远端 `~/newCarProject` 和 `~/ros2_ws` **一根手指都不碰**（那是同事的目标接口）。所有工作都发生在 Jetson `~/qt/` 下。
- `cockpit/` **不推**到 Jetson，任何时候都别 push 它。
- `mirror/` 下的中间产物（`__pycache__` / `.venv` / `log/` / `build/` / `install/`）不入库，见 `.gitignore`。
