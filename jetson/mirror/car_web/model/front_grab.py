"""
前侧扒手升降电机控制 - AQMD2403NS-M2B 直流有刷电机驱动器

硬件：
  - 驱动器型号：AQMD2403NS-M2B（与后侧升降相同）
  - 通信：RS485 Modbus-RTU（复用 rear_lift 串口）
  - 限位：SQ1 = 原点限位（顶部，收回状态），SQ2 = 行程限位（底部）

控制方式：485通讯控制 - 外接编码器位置闭环（0x0080 低字节 = 3）

设备地址：
  - 地址 1 = 后侧支腿升降（rear_lift 为串口宿主）
  - 地址 2 = 前侧扒手升降（本模块）

寄存器（参考 AQMD2403NS-M2B 手册，同后侧升降）：
  0x0018-0x0019  限位状态（读2寄存器），0x0000=触发, 0x0001=未触发
  0x0040  停止：写 0x0000 = 停止运行
  0x0044  释放：写 0x0001 = 释放电机
  0x0046  位置闭环转速，单位 RPM（绝对位置运动用）
  0x0047  位置控制类型：0=绝对位置，1=相对位置
  0x0048-0x0049  目标位置（32位高低字），绝对位置运动用
  0x00CF  SQ2复位：写 0x0003 = 复位SQ2
  0x700A  位置清零：写 0x0001 = 当前位置归零
  0x002C-0x002D  编码器当前位置（32位，只读）
"""
import time
import struct

from model import rear_lift
from tool.crc16_modbus import crc16_modbus
from tool.log_config import logger

# ==================== 串口（复用后侧升降串口）====================
ser = None
DEVICE_ADDR = 2  # 前侧扒手升降

# ==================== 位置与限位状态 ====================
_current_position = 0
_is_homed = False


# ==================== Modbus 工具函数 ====================
def _read_registers(reg_start, count):
    """读保持寄存器 0x03"""
    global ser
    cmd = [DEVICE_ADDR, 0x03, (reg_start >> 8) & 0xFF, reg_start & 0xFF, 0x00, count]
    crc = crc16_modbus(cmd)
    full = bytes(cmd) + crc
    try:
        rear_lift.ser.flushInput()
        rear_lift.ser.write(full)
        logger.info(f"[TX-扒手] 读寄存器 0x{reg_start:04X} x{count} => {full.hex(' ').upper()}")
        time.sleep(0.05)
        resp = rear_lift.ser.read(rear_lift.ser.in_waiting)
        logger.info(f"[RX-扒手] 读寄存器 0x{reg_start:04X} 响应({len(resp)}B) => {resp.hex(' ').upper()}")
        if len(resp) >= 5 and resp[0] == DEVICE_ADDR and resp[1] == 0x03:
            return resp[3:-2]
        return None
    except Exception as e:
        logger.error(f"前侧扒手读寄存器失败: {e}")
        return None


def _write_single_register(reg, value):
    """写单个寄存器 0x06"""
    global ser
    cmd = [DEVICE_ADDR, 0x06, (reg >> 8) & 0xFF, reg & 0xFF,
           (value >> 8) & 0xFF, value & 0xFF]
    crc = crc16_modbus(cmd)
    full = bytes(cmd) + crc
    try:
        rear_lift.ser.write(full)
        logger.info(f"[TX-扒手] 写寄存器 0x{reg:04X} = 0x{value:04X} => {full.hex(' ').upper()}")
        time.sleep(0.05)
        resp = rear_lift.ser.read(rear_lift.ser.in_waiting)
        if resp:
            logger.info(f"[RX-扒手] 写寄存器 0x{reg:04X} 响应({len(resp)}B) => {resp.hex(' ').upper()}")
        return True
    except Exception as e:
        logger.error(f"前侧扒手写寄存器 0x{reg:04X} 失败: {e}")
        return False


def _write_multiple_registers(reg_start, values):
    """写多个寄存器 0x10"""
    global ser
    count = len(values)
    data_bytes = []
    for v in values:
        data_bytes.extend([(v >> 8) & 0xFF, v & 0xFF])
    cmd = [DEVICE_ADDR, 0x10,
           (reg_start >> 8) & 0xFF, reg_start & 0xFF,
           0x00, count, count * 2] + data_bytes
    crc = crc16_modbus(cmd)
    full = bytes(cmd) + crc
    try:
        rear_lift.ser.write(full)
        logger.info(f"[TX-扒手] 写多寄存器 0x{reg_start:04X} x{count} => {full.hex(' ').upper()}")
        time.sleep(0.05)
        resp = rear_lift.ser.read(rear_lift.ser.in_waiting)
        if resp:
            logger.info(f"[RX-扒手] 写多寄存器 0x{reg_start:04X} 响应({len(resp)}B) => {resp.hex(' ').upper()}")
        return True
    except Exception as e:
        logger.error(f"前侧扒手写多寄存器失败: {e}")
        return False


def _bytes_to_s32(data):
    if data is None or len(data) < 4:
        return 0
    return struct.unpack('>i', bytes(data[:4]))[0]


def _s32_to_u16_pair(val):
    val = max(-2147483648, min(2147483647, val))
    return (val >> 16) & 0xFFFF, val & 0xFFFF


# ==================== 初始化 ====================
def grab_motor_init():
    global ser
    logger.info("开始初始化前侧扒手（复用后侧升降串口）")
    try:
        if rear_lift.ser is not None and rear_lift.ser.is_open:
            ser = rear_lift.ser
            logger.info("前侧扒手已复用后侧升降串口")
            _configure_driver()
            return ser
        else:
            logger.error("后侧升降串口未初始化，请先调用 rear_lift_init()")
            return None
    except Exception as e:
        logger.error(f"前侧扒手初始化失败：{e}", exc_info=True)
        return None


def _sq2_reset():
    """SQ2复位：写 0x0003 到寄存器 0x00CF"""
    _write_single_register(0x00CF, 0x0003)
    time.sleep(0.1)
    logger.info("前侧扒手 SQ2复位完成")


def _position_clear():
    """位置清零：写 0x0001 到寄存器 0x700A"""
    _write_single_register(0x700A, 0x0001)
    time.sleep(0.1)
    logger.info("前侧扒手 位置清零完成")


def _configure_driver():
    """
    配置驱动器：SQ2复位 → 读限位
    """
    # 1. SQ2复位
    _sq2_reset()

    # 2. 读限位，若SQ2触发则位置清零
    _, sq2, _ = read_limits()
    if sq2 is True:
        logger.info("前侧扒手 SQ2已触发，执行位置清零")
        _position_clear()
    else:
        logger.info("前侧扒手 SQ2未触发，跳过位置清零")



# ==================== 限位状态读取 ====================
def read_limits():
    """
    读取前侧扒手限位开关状态
    返回: (sq1_triggered, sq2_triggered, raw_data)
    """
    data = _read_registers(0x0018, 2)
    if data is None or len(data) < 4:
        return None, None, None
    sq1_raw = struct.unpack('>H', bytes(data[0:2]))[0]
    sq2_raw = struct.unpack('>H', bytes(data[2:4]))[0]
    # 0x0000=限位触发(到位), 0x0001=未触发
    sq1 = (sq1_raw == 0x0000)
    sq2 = (sq2_raw == 0x0000)
    logger.info(f"[限位-扒手] 0x0018=0x{sq1_raw:04X}(SQ1={sq1})  0x0019=0x{sq2_raw:04X}(SQ2={sq2})")
    return sq1, sq2, sq1_raw


# ==================== 电机停止 ====================
def _motor_stop_cmd():
    """电机停止：写 0x0040=停止 → 写 0x0044=释放"""
    _write_single_register(0x0040, 0x0000)
    time.sleep(0.05)
    _write_single_register(0x0044, 0x0001)


# ==================== 找零（SQ2归零校准）====================
def grab_home(timeout=15.0):
    """
    找零：发SQ2复位指令，驱动器自动运动到SQ2限位，到位后当前位置归零
    """
    global _current_position, _is_homed
    if ser is None or not ser.is_open:
        return False, "串口未初始化"

    logger.info("前侧扒手找零（SQ2复位→等待SQ2触发）...")

    _sq2_reset()

    start = time.time()
    triggered = False
    while time.time() - start < timeout:
        _, sq2, _ = read_limits()
        if sq2 is True:
            triggered = True
            logger.info("前侧扒手 SQ2触发，找零到位")
            break
        time.sleep(0.05)

    if triggered:
        _current_position = 0
        _is_homed = True
        logger.info("前侧扒手找零完成，位置=0")
        return True, "找零完成"
    else:
        logger.warning("前侧扒手找零超时，SQ2未触发")
        return False, "找零超时"


# ==================== 绝对位置移动 ====================
def grab_move_to(target_position, speed=60):
    """
    移动到绝对位置（非阻塞）
    写入指令即返回，驱动器自动执行位置闭环。
    """
    global _current_position
    if ser is None or not ser.is_open:
        return False, "串口未初始化"
    if not _is_homed:
        return False, "未找零，请先执行找零"

    speed = max(1, min(3000, int(speed)))
    high, low = _s32_to_u16_pair(target_position)

    _write_multiple_registers(0x0046, [speed, 0, high, low])
    _current_position = target_position
    logger.info(f"前侧扒手已发送绝对位置指令: speed={speed}RPM, target={target_position}")
    return True, f"已发送移动到 {target_position}"


def grab_get_position():
    """读取编码器当前位置（寄存器 0x002C-0x002D，32位只读）"""
    data = _read_registers(0x002C, 2)
    if data and len(data) >= 4:
        return _bytes_to_s32(data)
    return _current_position


def grab_is_homed():
    return _is_homed


def grab_stop():
    """扒手停止"""
    if ser is None or not ser.is_open:
        return False, "串口未初始化"
    _motor_stop_cmd()
    logger.info(f"前侧扒手 停止 | 地址={DEVICE_ADDR}")
    return True, "扒手停止"


def grab_speed_run(speed):
    """
    速度模式运行（寄存器 0x0040）
    :param speed: 有符号速度值，正=正向，负=反向，0=停止
    """
    if ser is None or not ser.is_open:
        return False, "串口未初始化"
    value = speed & 0xFFFF  # 有符号转16位无符号
    ok = _write_single_register(0x0040, value)
    if ok:
        direction = "正向" if speed > 0 else ("反向" if speed < 0 else "停止")
        logger.info(f"前侧扒手速度模式: {direction} speed={speed} (0x{value:04X})")
        return True, f"速度模式 {direction} speed={speed}"
    return False, "写入失败"
