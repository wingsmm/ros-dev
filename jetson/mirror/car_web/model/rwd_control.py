"""
后轮驱动控制 - FT-DM-01B 双路直流电机驱动器
电机1 寄存器：0x0004(方向) 0x0005(速度) 0x0006(刹车)
电机2 寄存器：0x0009(方向) 0x000A(速度) 0x000B(刹车)
协议：Modbus-RTU, 功能码 0x10(写多寄存器), 0x03(读保持寄存器)
"""
import serial
import time

from tool.crc16_modbus import crc16_modbus
from tool.log_config import logger

ser = None
# TODO: 改为你实际的串口（RS485转USB）
port = '/dev/serial1'
DEVICE_ADDR = 1  # 驱动器设备地址，出厂默认1


def rwd_motor_init():
    global ser
    logger.info("开始初始化后轮驱动串口")
    try:
        ser = serial.Serial(port, 9600, timeout=0.5)
        if not ser.is_open:
            ser.open()
        time.sleep(0.1)
        logger.info("后轮驱动串口初始化成功")
        return ser
    except FileNotFoundError:
        logger.error(f"错误：找不到串口 {port}，请检查接线")
        return None
    except serial.SerialException as e:
        logger.error(f"串口初始化失败：{e}")
        return None
    except Exception as e:
        logger.error(f"未知错误：{e}", exc_info=True)
        return None


def _get_start_addr(motor_id):
    """获取电机方向寄存器起始地址"""
    if motor_id == 1:
        return 0x0004
    elif motor_id == 2:
        return 0x0009
    else:
        raise ValueError(f"无效电机ID: {motor_id}")


def motor_run(motor_id=1, speed=50, direction=0):
    """
    电机运行控制
    :param motor_id: 1(电机1) 或 2(电机2)
    :param speed: 0-100 (%)，0=停止
    :param direction: 0=正转, 1=反转
    :return: (success, message)
    """
    global ser
    if ser is None or not ser.is_open:
        logger.error("后轮驱动：串口未初始化，请检查硬件连接和串口号")
        return False, "串口未初始化"

    if not (0 <= speed <= 100):
        logger.error(f"后轮驱动：速度参数错误 {speed}")
        return False, f"速度必须 0-100，当前：{speed}"
    if direction not in (0, 1):
        logger.error(f"后轮驱动：方向参数错误 {direction}")
        return False, f"方向只能 0(正转) 或 1(反转)，当前：{direction}"
    if motor_id not in (1, 2):
        logger.error(f"后轮驱动：电机ID参数错误 {motor_id}")
        return False, f"电机ID只能是 1 或 2"

    try:
        start_addr = _get_start_addr(motor_id)

        # 0x10 写多个寄存器：连续写方向 + 速度两个寄存器
        cmd = [
            DEVICE_ADDR,
            0x10,
            (start_addr >> 8) & 0xFF, start_addr & 0xFF,  # 起始地址
            0x00, 0x02,  # 寄存器数量（方向+速度）
            0x04,        # 字节数（2个寄存器 × 2字节）
            0x00, direction,  # 方向寄存器值
            0x00, speed       # 速度寄存器值
        ]

        crc_bytes = crc16_modbus(cmd)
        full_cmd = bytes(cmd) + crc_bytes

        ser.write(full_cmd)
        time.sleep(0.05)

        dir_text = "正转" if direction == 0 else "反转"
        msg = f"后轮电机{motor_id} {dir_text} 速度{speed}% | {full_cmd.hex(' ').upper()}"
        logger.info(msg)
        return True, msg

    except Exception as e:
        logger.error(f"后轮电机控制失败：{e}", exc_info=True)
        return False, f"控制失败：{str(e)}"


# ==================== 统一前进/后退控制 ====================
# 电机映射关系：
#   电机1（后右轮）：正转(0)=向后走，反转(1)=向前走
#   电机2（后左轮）：正转(0)=向前走，反转(1)=向后走
#
#  前进：电机1(反转=1) + 电机2(正转=0)
#  后退：电机1(正转=0) + 电机2(反转=1)

def rear_drive(direction=1, speed=50):
    """
    后轮统一前进/后退控制
    :param direction: 1=前进, 0=后退
    :param speed: 0-100
    """
    if direction == 1:
        # 前进
        ok1, msg1 = motor_run(motor_id=1, speed=speed, direction=1)  # 电机1反转→向前
        ok2, msg2 = motor_run(motor_id=2, speed=speed, direction=0)  # 电机2正转→向前
    else:
        # 后退
        ok1, msg1 = motor_run(motor_id=1, speed=speed, direction=0)  # 电机1正转→向后
        ok2, msg2 = motor_run(motor_id=2, speed=speed, direction=1)  # 电机2反转→向后

    if ok1 and ok2:
        action = "前进" if direction == 1 else "后退"
        msg = f"后轮 {action} 速度{speed}%"
        logger.info(msg)
        return True, msg
    else:
        return False, f"电机1:{msg1} | 电机2:{msg2}"


def rear_stop():
    """停止后轮两个电机"""
    motor_run(1, 0, 0)
    motor_run(2, 0, 0)
    logger.info("后轮已停止")
    return True, "后轮已停止"
