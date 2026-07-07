"""
车身倾角传感器 - Modbus-RTU
协议：功能码 0x03（读保持寄存器）
寄存器 0x0000 = X轴角度，返回值/100 = 实际角度（°）
"""
import serial
import time
import serial.tools.list_ports

from tool.crc16_modbus import crc16_modbus
from tool.log_config import logger

ser = None
DEVICE_ADDR = 1
# port = 'COM14'
port = '/dev/serial5'
BAUDRATE = 9600


def tilt_sensor_init(force_port=None):
    global ser
    p = force_port or port
    logger.info(f"开始初始化倾角传感器串口 {p}")
    try:
        ser = serial.Serial(p, BAUDRATE, timeout=0.5)
        time.sleep(0.1)
        logger.info(f"倾角传感器串口初始化成功: {p}")
        return True
    except Exception as e:
        logger.error(f"倾角传感器串口初始化失败: {e}")
        return False


def _read_holding_registers(reg_start, count=1):
    """读取保持寄存器（功能码 0x03）"""
    global ser
    if ser is None or not ser.is_open:
        return None
    cmd = [DEVICE_ADDR, 0x03, (reg_start >> 8) & 0xFF, reg_start & 0xFF,
           0x00, count]
    crc = crc16_modbus(cmd)
    full = bytes(cmd) + crc
    try:
        ser.write(full)
        logger.info(f"[TX-倾角] 读取寄存器 0x{reg_start:04X} => {full.hex(' ').upper()}")
        time.sleep(0.1)
        resp = ser.read(7)  # addr + func + count + data(2B) + CRC(2B) = 7B
        if len(resp) >= 5:
            logger.info(f"[RX-倾角] => {resp.hex(' ').upper()}")
            return resp
        else:
            logger.warning(f"[RX-倾角] 响应长度不足: {len(resp)}B")
            return None
    except Exception as e:
        logger.error(f"倾角传感器读寄存器失败: {e}")
        return None


def read_x_angle():
    """
    读取X轴倾角
    :return: (角度值°, raw原始值) 或 (None, None)
    """
    resp = _read_holding_registers(0x0000, 1)
    if resp is None or len(resp) < 5:
        return None, None
    # resp[3] = high byte, resp[4] = low byte
    raw = (resp[3] << 8) | resp[4]
    if raw >= 0x8000:
        raw -= 0x10000  # 有符号16位转负数
    angle = raw / 100.0
    logger.info(f"倾角传感器 X轴: raw=0x{raw:04X}({raw}) -> {angle:.2f}°")
    return angle, raw
