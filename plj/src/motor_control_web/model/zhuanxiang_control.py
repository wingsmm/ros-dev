import threading

import serial
import time

# 导入日志器
from tool.log_config import logger

# 全局串口对象
ser = None
port = '/dev/serial4' #'/dev/serial4'

# 电机走一圈（27 * 32） 1728
# 小车底盘电机走一圈是 100 * 64   6400走90度

# 接收缓存
recv_buffer = bytearray()

# 全局最新电机数据（实时更新）
motor_data = {
    "motor1_current": 0,
    "motor2_current": 0,
    "motor1_target": 0,
    "motor2_target": 0,
    "motor1_origin": 0,
    "motor2_origin": 0,
    "raw_frame": ""
}


def zhuanxiang_motor_init():
    global ser
    logger.info("开始初始化底盘转向电机串口连接")
    try:
        ser = serial.Serial(port, 115200, timeout=0.5)
        if not ser.is_open:
            ser.open()
        time.sleep(0.1)
        logger.info("电机串口初始化成功！")
        return ser

    except FileNotFoundError:
        error_msg = f"错误：找不到串口 COM3，请检查串口是否存在或接线是否正确"
        logger.error(error_msg)
        return None
    except serial.SerialException as e:
        error_msg = f"串口初始化失败：{e}"
        logger.error(error_msg)
        return None
    except Exception as e:
        error_msg = f"未知错误：{e}"
        logger.error(error_msg, exc_info=True)
        return None


def build_x_packet(addr: int, target_pos: int, speed: int):
    """
    构建 X-Protocol 数据包 → 支持 正负位置
    """
    status = 7  # 状态位：到位停+原点停+编码器归零

    # ==============================================
    # ✅ 关键：支持负数（int32 补码处理）
    # ==============================================
    target_pos = target_pos & 0xFFFFFFFF  # 转成32位无符号

    # 拆分 4 字节位置（高字节在前）
    pos_b4 = (target_pos >> 24) & 0xFF
    pos_b3 = (target_pos >> 16) & 0xFF
    pos_b2 = (target_pos >> 8) & 0xFF
    pos_b1 = target_pos & 0xFF

    # 拆分 2 字节速度
    speed_b1 = (speed >> 8) & 0xFF
    speed_b2 = speed & 0xFF

    # 状态
    sta_b1 = (status >> 8) & 0xFF
    sta_b2 = status & 0xFF

    # 构建帧
    frame = [
        0xAA, 0x55,
        0x0D,
        addr & 0xFF,
        pos_b4, pos_b3, pos_b2, pos_b1,
        speed_b1, speed_b2,
        sta_b1, sta_b2
    ]

    # 校验和
    checksum = sum(frame) & 0xFF
    frame.append(checksum)

    return bytes(frame)

def send_motor_cmd(addr,target_position,speed):
    global ser
    # 生成数据包
    send_data = build_x_packet(addr, target_position, speed)
    # 打印
    hex_str = ' '.join(f'{b:02X}' for b in send_data)
    logger.info(f"✅ 发送帧： {hex_str}")
    # 发送
    if ser and ser.is_open:
        ser.write(send_data)
        print("✅ 发送成功")
    else:
        print("❌ 串口未打开")


# ===================== 解析接收的数据 =====================
def parse_motor_frame(frame):
    try:
        # 你的帧长度 = 0x17 = 23 字节
        if len(frame) != 23:
            return

        # 帧结构：
        # AA 55 17 06 [1#当前4] [2#当前4] [1#目标4] [2#目标4] [IO2] 校验
        motor1_current = int.from_bytes(frame[4:8],  "big", signed=True)
        motor2_current = int.from_bytes(frame[8:12], "big", signed=True)
        motor1_target  = int.from_bytes(frame[12:16],"big", signed=True)
        motor2_target  = int.from_bytes(frame[16:20],"big", signed=True)
        io_state       = int.from_bytes(frame[20:22],"big")

        # ====================== 正确限位解析 ======================
        # bit0 = 1 → 电机1限位未触发
        # bit0 = 0 → 电机1限位触发
        motor1_limit = (io_state >> 0) & 1
        motor1_limit_triggered = (motor1_limit == 0)  # True=触发

        # bit1 = 1 → 电机2限位未触发
        # bit1 = 0 → 电机2限位触发
        motor2_limit = (io_state >> 1) & 1
        motor2_limit_triggered = (motor2_limit == 0)  # True=触发

        # 更新全局数据
        motor_data["motor1_current"] = motor1_current
        motor_data["motor2_current"] = motor2_current
        motor_data["motor1_target"] = motor1_target
        motor_data["motor2_target"] = motor2_target
        motor_data["motor1_limit"] = motor1_limit  # 1=未触发 0=触发
        motor_data["motor2_limit"] = motor2_limit  # 1=未触发 0=触发
        motor_data["motor1_limit_triggered"] = motor1_limit_triggered
        motor_data["motor2_limit_triggered"] = motor2_limit_triggered
        motor_data["raw_frame"] = frame.hex(' ')

        # 日志输出（实时查看）
        # logger.info(f"""
        # 📥 电机1# 当前: {motor1_current}  目标: {motor1_target}  限位状态: {motor1_limit} (触发={motor1_limit_triggered})
        # 📥 电机2# 当前: {motor2_current}  目标: {motor2_target}  限位状态: {motor2_limit} (触发={motor2_limit_triggered})
        # """)

    except Exception as e:
        logger.error(f"解析错误: {e}")

# ===================== 485 持续接收线程（永不退出） =====================
def recv_thread():
    global recv_buffer
    while True:
        if not ser or not ser.is_open:
            time.sleep(0.1)
            continue

        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                recv_buffer.extend(data)

                # 找帧头 AA 55
                while len(recv_buffer) >= 2:
                    if recv_buffer[0] == 0xAA and recv_buffer[1] == 0x55:
                        break
                    recv_buffer.pop(0)

                # 按帧长截取
                if len(recv_buffer) >= 3:
                    frame_len = recv_buffer[2]
                    if len(recv_buffer) >= frame_len:
                        frame = recv_buffer[:frame_len]
                        recv_buffer = recv_buffer[frame_len:]
                        parse_motor_frame(frame)

        except Exception as e:
            logger.error(f"接收异常：{e}")
            time.sleep(0.1)

# ===================== 启动接收 =====================
def start_receive():
    t = threading.Thread(target=recv_thread, daemon=True)
    t.start()
    logger.info("✅ 485 实时监听已启动")

# ====================== 主程序 ======================
if __name__ == '__main__':
    zhuanxiang_motor_init()

    # 你的参数 ✅ 支持负数
    addr = 33
    target_position = 5000   # <----- 这里直接写 -100
    speed = 1000

    # 生成数据包
    send_motor_cmd(addr, target_position, speed)