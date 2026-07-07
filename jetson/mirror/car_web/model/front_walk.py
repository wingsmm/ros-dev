# 前轮行走电机（左右各1个，共2个）
# 功能：前进 / 后退 / 停止
# 驱动器：单串口控制两个驱动器，通过Modbus地址区分
#
# 寄存器（保持寄存器，0x10写多个）：
#   0x0008  速度（转/分钟），用0x10写入1个寄存器
#
# 线圈寄存器（0x05写单个线圈）：
#   0x0004  正转点动  ON=一直正转  OFF=停止
#   0x0005  反转点动  ON=一直反转  OFF=停止
import serial
import time
import struct

from tool.crc16_modbus import crc16_modbus
from tool.log_config import logger

ser = None
port = '/dev/serial3'

BAUDRATE = 9600

# 驱动器Modbus地址：左轮=2，右轮=1（根据实际拨码）
ADDR_LEFT = 2
ADDR_RIGHT = 1


def _get_addr(motor_id):
    return ADDR_RIGHT if motor_id == 1 else ADDR_LEFT  # 1=右轮(addr=1), 2=左轮(addr=2)


# ==================== Modbus 工具函数 ====================
def _write_single_register(addr, reg, value):
    """写单个寄存器 0x06"""
    cmd = [addr, 0x06,
           (reg >> 8) & 0xFF, reg & 0xFF,
           (value >> 8) & 0xFF, value & 0xFF]
    crc = crc16_modbus(cmd)
    full = bytes(cmd) + crc
    try:
        ser.write(full)
        logger.info(f"[TX-前轮] addr={addr} 写寄存器 0x{reg:04X}=0x{value:04X} => {full.hex(' ').upper()}")
        time.sleep(0.05)
        resp = ser.read(ser.in_waiting)
        if resp:
            logger.info(f"[RX-前轮] addr={addr} 响应({len(resp)}B) => {resp.hex(' ').upper()}")
        return True
    except Exception as e:
        logger.error(f"[前轮] 写寄存器 0x{reg:04X} 失败: {e}")
        return False


def _write_multiple_registers(addr, reg_start, values):
    """写多个寄存器 0x10"""
    count = len(values)
    data_bytes = []
    for v in values:
        data_bytes.extend([(v >> 8) & 0xFF, v & 0xFF])
    cmd = [addr, 0x10,
           (reg_start >> 8) & 0xFF, reg_start & 0xFF,
           0x00, count,
           count * 2] + data_bytes
    crc = crc16_modbus(cmd)
    full = bytes(cmd) + crc
    try:
        ser.write(full)
        logger.info(f"[TX-前轮] addr={addr} 写多寄存器 0x{reg_start:04X} x{count} => {full.hex(' ').upper()}")
        time.sleep(0.05)
        resp = ser.read(ser.in_waiting)
        if resp:
            logger.info(f"[RX-前轮] addr={addr} 响应({len(resp)}B) => {resp.hex(' ').upper()}")
        return True
    except Exception as e:
        logger.error(f"[前轮] 写多寄存器失败: {e}")
        return False


def _write_single_coil(addr, coil, on=True):
    """写单个线圈 0x05，ON=0xFF00，OFF=0x0000"""
    val = 0xFF00 if on else 0x0000
    cmd = [addr, 0x05,
           (coil >> 8) & 0xFF, coil & 0xFF,
           (val >> 8) & 0xFF, val & 0xFF]
    crc = crc16_modbus(cmd)
    full = bytes(cmd) + crc
    try:
        ser.write(full)
        state = 'ON' if on else 'OFF'
        logger.info(f"[TX-前轮] addr={addr} 写线圈 0x{coil:04X}={state} => {full.hex(' ').upper()}")
        time.sleep(0.05)
        resp = ser.read(ser.in_waiting)
        if resp:
            logger.info(f"[RX-前轮] addr={addr} 响应({len(resp)}B) => {resp.hex(' ').upper()}")
        return True
    except Exception as e:
        logger.error(f"[前轮] 写线圈 0x{coil:04X} 失败: {e}")
        return False


# ==================== 初始化 ====================
def front_walk_init():
    global ser
    logger.info("开始初始化前轮行走串口")
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=0.5)
        if not ser.is_open:
            ser.open()
        time.sleep(0.2)
        logger.info(f"前轮行走串口初始化成功 port={port} baud={BAUDRATE}")
        return ser
    except Exception as e:
        logger.error(f"前轮行走初始化失败: {e}")
        return None


# ==================== 电机控制 ====================
def front_walk_run(motor_id=1, speed=50, direction=0):
    """
    前轮行走点动运行
    :param motor_id: 1=左轮，2=右轮
    :param speed:    速度（转/分钟），用0x10写入寄存器0x0008
    :param direction: 0=正转（前进），1=反转（后退）
    """
    global ser
    if ser is None or not ser.is_open:
        return False, "串口未初始化"

    addr = _get_addr(motor_id)
    side = '左轮' if motor_id == 1 else '右轮'

    # 1. 用0x10写速度寄存器 0x0008（1个寄存器，2字节数据）
    speed = max(0, min(65535, int(speed)))
    _write_multiple_registers(addr, 0x0008, [speed])
    time.sleep(0.02)

    # 2. 先关闭反向线圈，再开启正向线圈（或反之），避免冲突
    if direction == 0:
        _write_single_coil(addr, 0x0005, on=False)  # 先关反转
        time.sleep(0.02)
        _write_single_coil(addr, 0x0004, on=True)   # 开正转
    else:
        _write_single_coil(addr, 0x0004, on=False)  # 先关正转
        time.sleep(0.02)
        _write_single_coil(addr, 0x0005, on=True)   # 开反转

    dir_str = '正转' if direction == 0 else '反转'
    logger.info(f"[前轮] {side}(addr={addr}) {dir_str} speed={speed}")
    return True, f"{side} {dir_str} speed={speed}"


def front_walk_stop(motor_id=1):
    """
    前轮停止：关闭正转+反转线圈
    :param motor_id: 1=左轮，2=右轮
    """
    global ser
    if ser is None or not ser.is_open:
        return False, "串口未初始化"

    addr = _get_addr(motor_id)
    side = '左轮' if motor_id == 1 else '右轮'

    _write_single_coil(addr, 0x0004, on=False)  # 关正转
    _write_single_coil(addr, 0x0005, on=False)  # 关反转

    logger.info(f"[前轮] {side}(addr={addr}) 停止")
    return True, f"{side} 已停止"
