# cockpit - Jetson 本机 Qt 最小壳

`jetson/mirror/cockpit/` 同步到板上 `~/qt/cockpit/`，在 Jetson 本机跑。
与 `jetson/cockpit/`（VMware 观测端）分开维护。

本阶段只有：状态 / topic 诊断 / 五键 `/cmd_vel` 干跑 / 内嵌 Web控制窗口。不含 SSH、RViz、雷达一键。

`WEB_CONTROL_URL`（`.env`）默认 `http://172.0.0.82:8080/ctl`；「Web控制」打开 **PyQt 内嵌窗口**（优先 `QWebEngineView`，否则 `QWebView`），不走系统浏览器。

WebKit 路径会注入 `fetch` polyfill（`control.js` 依赖 Fetch；旧 QtWebKit 没有）。缺包时：

```bash
sudo apt install -y python3-pyqt5.qtwebengine
# 或
sudo apt install -y python3-pyqt5.qtwebkit
```


## 同步与运行

```bash
# 开发机
bash jetson/scripts/jetson.sh push cockpit --yes

# Jetson（需桌面或 DISPLAY）
cd ~/qt/cockpit
cp -n .env.example .env
pip3 install --user -r requirements.txt   # 或 apt 装 python3-pyqt5
bash run.sh
```

## 目录

```text
app.py / main_window.py / run.sh
core/   config, logging, ros2_control, ros2_probe
ui/     status_panel, teleop_panel, topic_panel
```
