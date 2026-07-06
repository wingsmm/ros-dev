import serial
import time

from tool.crc16_modbus import crc16_modbus
# 导入日志器
from tool.log_config import logger

# 全局串口对象
ser = None
# port = '/dev/serial3' #这个串口是3568板子
port = '/dev/serial1'  #这个是nvidia板子

def chassis_motor_init():
    global ser
    logger.info("开始初始化电机串口连接")  # 替换print
    try:
        ser = serial.Serial(port, 9600, timeout=0.5)
        # 确保串口已打开
        if not ser.is_open:
            ser.open()
        # 串口初始化后建议短暂延时，让设备稳定
        time.sleep(0.1)
        logger.info("电机串口初始化成功！")  # 替换print
        return ser  # 初始化成功返回串口对象

    except FileNotFoundError:
        error_msg = f"错误：找不到串口 ，请检查串口是否存在或接线是否正确"
        logger.error(error_msg)  # 替换print
        return None
    except serial.SerialException as e:
        error_msg = f"串口初始化失败：{e}"
        logger.error(error_msg)  # 替换print
        return None
    except Exception as e:
        error_msg = f"未知错误：{e}"
        logger.error(error_msg, exc_info=True)  # 替换print，exc_info记录堆栈
        return None

def chassis_motor_run(motor_id=1, speed=50, direction=0):
    global ser
    slave_id = 1
    if ser is None or not ser.is_open:
        error_msg = "错误：串口未初始化"
        logger.error(error_msg)
        return False, error_msg
    if not (0 <= speed <= 100):
        error_msg = f"错误：速度必须 0-100，当前：{speed}"
        logger.error(error_msg)
        return False, error_msg
    if direction not in (0, 1):
        error_msg = f"错误：方向只能 0(正转) 或 1(反转)"
        logger.error(error_msg)
        return False, error_msg
    if motor_id not in (1, 2):
        error_msg = f"错误：电机只能是 1 或 2"
        logger.error(error_msg)
        return False, error_msg

    try:
        if motor_id == 1:
            start_addr = 0x0004  # 电机1
        else:
            start_addr = 0x0009  # 电机2（你确认的正确地址）

        # 指令构造（和你格式完全一致）
        cmd = [
            slave_id,
            0x10,
            (start_addr >> 8) & 0xFF, start_addr & 0xFF,
            0x00, 0x02,
            0x04,
            0x00, direction,
            0x00, speed
        ]

        crc_bytes = crc16_modbus(cmd)
        full_cmd = bytes(cmd) + crc_bytes

        ser.write(full_cmd)
        time.sleep(0.05)

        dir_text = "正转" if direction == 0 else "反转"
        success_msg = f"电机{motor_id} {dir_text} 速度{speed} | 指令：{full_cmd.hex(' ').upper()}"
        logger.info(success_msg)
        return True, success_msg

    except Exception as e:
        error_msg = f"电机控制失败：{str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg