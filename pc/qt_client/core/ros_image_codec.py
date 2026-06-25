"""JPEG -> sensor_msgs/Image (rgb8) via Qt QImage."""

from __future__ import annotations

from PyQt5.QtGui import QImage


def jpeg_to_rgb8(jpeg: bytes) -> tuple[int, int, bytes]:
    qimg = QImage.fromData(jpeg)
    if qimg.isNull():
        raise ValueError("invalid JPEG")
    qimg = qimg.convertToFormat(QImage.Format_RGB888)
    width = qimg.width()
    height = qimg.height()
    bytes_per_line = qimg.bytesPerLine()
    total = height * bytes_per_line
    ptr = qimg.bits()
    ptr.setsize(total)
    raw = bytes(ptr)
    row_bytes = width * 3
    if bytes_per_line == row_bytes:
        return width, height, raw
    rows = [raw[y * bytes_per_line : y * bytes_per_line + row_bytes] for y in range(height)]
    return width, height, b"".join(rows)
