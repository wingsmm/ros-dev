"""Embedded car_web page in a PyQt web window (WebEngine or WebKit)."""

from __future__ import annotations

from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QAction, QMainWindow, QMessageBox, QToolBar, QVBoxLayout, QWidget


def _probe_backends() -> tuple[str, str]:
    """Return (backend, error_detail). backend is webengine|webkit|."""
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401

        return "webengine", ""
    except Exception as eng_exc:
        eng_err = str(eng_exc)
    try:
        from PyQt5.QtWebKitWidgets import QWebView  # noqa: F401

        return "webkit", ""
    except Exception as kit_exc:
        return "", "WebEngine: %s；WebKit: %s" % (eng_err, kit_exc)


class WebControlWindow(QMainWindow):
    def __init__(self, url: str, backend: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Web控制")
        self.resize(1100, 760)
        self._url = url
        self._backend = backend

        toolbar = QToolBar("导航", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        act_reload = QAction("刷新", self)
        act_reload.triggered.connect(self.reload)
        toolbar.addAction(act_reload)

        act_home = QAction("主页", self)
        act_home.triggered.connect(self.go_home)
        toolbar.addAction(act_home)

        if backend == "webengine":
            from PyQt5.QtWebEngineWidgets import QWebEngineView

            self._view = QWebEngineView(self)
            self.setCentralWidget(self._view)
        else:
            from PyQt5.QtWebKitWidgets import QWebView

            self._view = QWebView(self)
            self.setCentralWidget(self._view)

        self._view.load(QUrl(url))

    def go_home(self) -> None:
        self._view.load(QUrl(self._url))

    def reload(self) -> None:
        self._view.reload()

    def navigate(self, url: str) -> None:
        self._url = url
        self._view.load(QUrl(url))


def open_or_raise_web_control(parent, url: str, existing: WebControlWindow | None):
    """Open embedded Qt web window; reuse existing if still visible."""
    url = (url or "").strip()
    if not url:
        return existing

    backend, detail = _probe_backends()
    if not backend:
        QMessageBox.warning(
            parent,
            "Web控制",
            "需要 PyQt 网页组件，任选其一安装：\n"
            "  sudo apt install -y python3-pyqt5.qtwebengine\n"
            "  sudo apt install -y python3-pyqt5.qtwebkit\n\n"
            "详情：%s" % (detail or "import failed"),
        )
        return existing

    if existing is not None and existing.isVisible():
        existing.navigate(url)
        existing.raise_()
        existing.activateWindow()
        return existing

    window = WebControlWindow(url, backend=backend, parent=parent)
    window.show()
    return window
