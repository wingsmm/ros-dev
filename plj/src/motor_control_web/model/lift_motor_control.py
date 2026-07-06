import serial
import time

from tool.crc16_modbus import crc16_modbus
# 导入日志器
from tool.log_config import logger

# 全局串口对象
ser = None
# port = '/dev/serial2' # 此串口是3568板子
port = '/dev/serial2'  #此串口是nvidia板子

def motor_init():
    global ser
    logger.info("开始初始化电机串口连接")  # 替换print
    try:
        ser = serial.Serial(port, 57600, timeout=0.5)
        # 确保串口已打开
        if not ser.is_open:
            ser.open()
        # 串口初始化后建议短暂延时，让设备稳定
        time.sleep(0.1)
        logger.info("电机串口初始化成功！")  # 替换print
        return ser  # 初始化成功返回串口对象

    except FileNotFoundError:
        error_msg = f"错误：找不到串口 COM3，请检查串口是否存在或接线是否正确"
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


def motor_forward(motor_id=1):  # 正转向上运行
    global ser
    # 1. 检查串口是否初始化
    if ser is None or not ser.is_open:
        error_msg = "错误：串口未初始化"
        logger.error(error_msg)  # 替换print
        return False, error_msg
    try:
        # 2. 构造基础指令（16进制）：01 06 03 09 00 01
        base_cmd = [motor_id, 0x06, 0x03, 0x09, 0x00, 0x01]
        # 3. 计算CRC16校验码并追加到指令末尾
        crc_bytes = crc16_modbus(base_cmd)
        full_cmd = bytes(base_cmd) + crc_bytes  # 完整指令（带校验）
        # 4. 发送指令到串口
        ser.write(full_cmd)
        time.sleep(0.05)  # 短暂延时确保指令发送完成
        # 5. 可选：读取电机返回的响应（如果需要确认执行结果）
        # response = ser.read(8)  # 读取8字节响应
        success_msg = f"电机{motor_id}正转指令发送成功，指令（16进制）：{full_cmd.hex(' ')}"
        logger.info(success_msg)  # 替换print
        return True, success_msg
    except Exception as e:
        error_msg = f"正转执行失败：{str(e)}"
        logger.error(error_msg, exc_info=True)  # 替换print
        return False, error_msg


def motor_backward(motor_id):  # 反转下降
    global ser
    # 1. 检查串口是否初始化
    if ser is None or not ser.is_open:
        error_msg = "错误：串口未初始化"
        logger.error(error_msg)  # 替换print
        return False, error_msg
    try:
        # 2. 构造基础指令（16进制）：01 06 03 09 00 01
        base_cmd = [motor_id, 0x06, 0x03, 0x0B, 0x00, 0x01]
        # 3. 计算CRC16校验码并追加到指令末尾
        crc_bytes = crc16_modbus(base_cmd)
        full_cmd = bytes(base_cmd) + crc_bytes  # 完整指令（带校验）
        # 4. 发送指令到串口
        ser.write(full_cmd)
        time.sleep(0.05)  # 短暂延时确保指令发送完成
        # 5. 可选：读取电机返回的响应（如果需要确认执行结果）
        # response = ser.read(8)  # 读取8字节响应
        success_msg = f"电机{motor_id}反转指令发送成功，指令（16进制）：{full_cmd.hex(' ')}"
        logger.info(success_msg)  # 替换print
        return True, success_msg
    except Exception as e:
        error_msg = f"反转执行失败：{str(e)}"
        logger.error(error_msg, exc_info=True)  # 替换print
        return False, error_msg


def motor_stop(motor_id=1, zf=1):  # 电机停止
    global ser
    # 1. 检查串口是否初始化
    if ser is None or not ser.is_open:
        error_msg = "错误：串口未初始化"
        logger.error(error_msg)  # 替换print
        return False, error_msg
    try:
        if zf == 1:
            base_cmd = [motor_id, 0x06, 0x03, 0x09, 0x00, 0x00]
            crc_bytes = crc16_modbus(base_cmd)
            full_cmd = bytes(base_cmd) + crc_bytes  # 完整指令（带校验）
            # 4. 发送指令到串口
            ser.write(full_cmd)
            time.sleep(0.05)  # 短暂延时确保指令发送完成
            success_msg = f"电机{motor_id}正转已停止，指令（16进制）：{full_cmd.hex(' ')}"
            logger.info(success_msg)  # 替换print
            return True, success_msg
        else:
            base_cmd = [motor_id, 0x06, 0x03, 0x0B, 0x00, 0x00]
            crc_bytes = crc16_modbus(base_cmd)
            full_cmd = bytes(base_cmd) + crc_bytes  # 完整指令（带校验）
            ser.write(full_cmd)
            time.sleep(0.05)  # 短暂延时确保指令发送完成
            success_msg = f"电机{motor_id}反转已停止，指令（16进制）：{full_cmd.hex(' ')}"
            logger.info(success_msg)  # 替换print
            return True, success_msg
    except Exception as e:
        error_msg = f"停止执行失败：{str(e)}"
        logger.error(error_msg, exc_info=True)  # 替换print
        return False, error_msg


"""
    读取限位信号
    参数: device_addr - 要读取的机械地址
    返回: 限位状态（True=触发，False=未触发），失败返回None
    读返回的4：0000 0000 : 3为反转状态，4为正转状态，5是下限位，6是上限位
"""
def read_limit_switch(device_addr=1):
    global ser
    # 第一步：检查串口是否已初始化
    if ser is None or not ser.is_open:
        error_msg = "错误：串口未初始化或已关闭！"
        logger.error(error_msg)  # 替换print
        return None
    try:
        base_cmd = bytes([device_addr, 0x03, 0x0b, 0x03, 0x00, 0x01])
        crc_bytes = crc16_modbus(base_cmd)
        full_cmd = bytes(base_cmd) + crc_bytes  # 完整指令（带校验）

        # 清空缓冲区，避免脏数据
        ser.flushInput()
        ser.flushOutput()

        # 发送指令
        ser.write(full_cmd)
        send_msg = f"已发送限位读取指令: {[hex(b) for b in full_cmd]}"
        logger.info(send_msg)  # 替换print

        # 等待响应（可根据电机实际响应速度调整）
        time.sleep(0.05)

        # 读取返回数据
        response = ser.read(ser.in_waiting)

        if len(response) == 0:
            warn_msg = "未接收到限位信号响应"
            logger.warning(warn_msg)  # 替换print
            return None

        recv_msg = f"接收到响应数据: {[hex(b) for b in response]}"
        logger.info(recv_msg)  # 替换print

        # 补充：解析响应数据（原有逻辑补全）
        if len(response) >= 5 and response[0] == device_addr and response[1] == 0x03:
            limit_status = response[4]
            binary_str = format(limit_status, '08b')
            logger.info(f"limit_status(二进制): {binary_str}")
            # 定义每一位的含义（请根据你的实际业务场景修改）
            bit_definitions = {
                0: "",
                1: "",
                2: "",
                3: "反转状态",
                4: "正转状态",
                5: "下限位",
                6: "上限位",
                7: ""
            }
            # 解析每一位的状态（使用位运算，更高效准确）
            status_result = {}  # 存储有效位的解析结果
            for bit_index in bit_definitions:
                # 跳过未定义的位
                if not bit_definitions[bit_index]:
                    continue
                # 从binary_str中按下标取值（直接解析字符串，而非位运算）
                bit_value = int(binary_str[bit_index])  # binary_str[bit_index]是字符'0'/'1'，转成整数
                # 状态描述（可根据你的业务调整文字）
                status_desc = "触发" if bit_value else "未触发"
                if "状态" in bit_definitions[bit_index]:
                    status_desc = "运行" if bit_value else "停止"

                # 记录结果并打印日志
                status_result[bit_definitions[bit_index]] = bit_value
                logger.info(f"{bit_definitions[bit_index]}: {status_desc} (值: {bit_value})")
            return True,f"返回状态: {binary_str}"
        else:
            logger.error(f"响应数据解析失败，响应长度：{len(response)}，内容：{[hex(b) for b in response]}")
            return False,f"响应数据解析失败，响应长度：{len(response)}，内容：{[hex(b) for b in response]}"
    except serial.SerialException as e:
        error_msg = f"串口通信错误：{e}"
        logger.error(error_msg, exc_info=True)  # 替换print
        return None
    except Exception as e:
        error_msg = f"读取限位信号失败：{e}"
        logger.error(error_msg, exc_info=True)  # 替换print
        return False,f"读取限位信号失败：{e}"


