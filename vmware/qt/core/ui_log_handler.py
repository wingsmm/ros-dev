import logging

from PyQt5.QtCore import QObject, pyqtSignal


class UiLogSignaler(QObject):
    line = pyqtSignal(str)


class UiLogHandler(logging.Handler):
    def __init__(self, signaler):
        super(UiLogHandler, self).__init__()
        self._signaler = signaler
        self.setLevel(logging.INFO)
        self.setFormatter(
            logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
        )

    def emit(self, record):
        try:
            msg = self.format(record)
            self._signaler.line.emit(msg)
        except Exception:
            self.handleError(record)
