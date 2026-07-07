"""
前轮转向控制 - FT-DM-01B 双路直流电机驱动器 + USB角度传感器闭环控制

电机控制（与后轮驱动共用相同串口，靠设备地址区分）：
  - 电机1（右转向轮）= 地址2, 0x0004方向, 0x0005速度
  - 电机2（左转向轮）= 地址2, 0x0009方向, 0x000A速度

角度传感器：通过 USB 串口持续读取电压 → 线性换算为角度
"""
import serial
import time
import threading

from tool.crc16_modbus import crc16_modbus
from tool.log_config import logger

# ==================== 电机控制串口（复用后轮驱动串口）====================
from model import rwd_control

ser = None  # 在 steer_motor_init() 中连接到 rwd_control.ser
DEVICE_ADDR = 2  # 驱动器设备地址（地址1=后轮, 地址2=转向）

# ==================== 角度传感器串口（Modbus RTU）====================
angle_ser = None
ANGLE_PORT = '/dev/serial4'  # 根据实际修改

# 角度传感器 Modbus 参数
SENSOR_ADDR = 0x01  # 传感器模块设备地址

# 全局角度数据
_left_angle = 0.0       # 左轮角度（度）
_left_voltage = 0.0     # 左轮电压
_right_angle = 0.0      # 右轮角度（度）
_right_voltage = 0.0    # 右轮电压
steer_angle = 0.0       # 兼容旧接口（=左轮角度）
steer_voltage = 0.0     # 兼容旧接口（=左轮电压）
_angle_lock = threading.Lock()
_motor_lock = threading.Lock()  # 串口写入锁，防止多线程冲突

# 转向死区（角度误差在此范围内认为已到位）
DEAD_ZONE = 2.0  # 度（留2°余量减少惯性过冲）


# ==================== 初始化 ====================
def steer_motor_init():
    global ser
    logger.info("开始初始化转向电机（复用后轮驱动串口）")
    try:
        if rwd_control.ser is not None and rwd_control.ser.is_open:
            ser = rwd_control.ser
            logger.info("转向电机已复用后轮驱动串口")
            return ser
        else:
            logger.error("后轮驱动串口未初始化，请先调用 rwd_motor_init()")
            return None
    except Exception as e:
        logger.error(f"转向电机初始化失败：{e}", exc_info=True)
        return None


def angle_sensor_init():
    """初始化角度传感器串口，启动持续读取线程"""
    global angle_ser
    try:
        angle_ser = serial.Serial(ANGLE_PORT, 9600, timeout=0.5)
        if not angle_ser.is_open:
            angle_ser.open()
        logger.info(f"角度传感器串口初始化成功 port={ANGLE_PORT}")
        t = threading.Thread(target=_angle_read_loop, daemon=True)
        t.start()
        return angle_ser
    except Exception as e:
        logger.error(f"角度传感器初始化失败: {e}")
        return None


# ==================== 角度读取（Modbus RTU 后台线程）====================
def _read_sensor(register_count, label=""):
    """发送Modbus 0x04指令并返回原始响应"""
    cmd = [SENSOR_ADDR, 0x04, 0x00, 0x00, 0x00, register_count]
    crc = crc16_modbus(cmd)
    full = bytes(cmd) + crc
    angle_ser.flushInput()
    angle_ser.write(full)
    # logger.info(f"[TX-传感器{label}] 读{register_count}个寄存器 => {full.hex(' ').upper()}")
    time.sleep(0.05)
    resp = angle_ser.read(angle_ser.in_waiting)
    # logger.info(f"[RX-传感器{label}] 响应({len(resp)}B) => {resp.hex(' ').upper()}")
    return resp


def _raw_to_voltage(raw):
    """原始值→电压: (raw - 30000) * 0.001"""
    return (raw - 30000) * 0.001


def _voltage_to_angle(voltage):
    """电压→角度: 0-5V → 0-360°"""
    return voltage * 72.0  # 360° / 5V = 72°/V


def _angle_read_loop():
    """后台持续读取左右两个传感器"""
    global _left_angle, _left_voltage, _right_angle, _right_voltage
    global steer_angle, steer_voltage
    while True:
        if not angle_ser or not angle_ser.is_open:
            time.sleep(0.1)
            continue
        try:
            # ---- 读左轮传感器: 01 04 00 00 00 02 (2个寄存器=CH1+CH2) ----
            resp_left = _read_sensor(2, label="左")
            left_v, left_a = None, None
            if len(resp_left) >= 7 and resp_left[0] == SENSOR_ADDR and resp_left[1] == 0x04:
                ch2_raw = (resp_left[5] << 8) | resp_left[6]
                left_v = _raw_to_voltage(ch2_raw)
                left_a = _voltage_to_angle(left_v)

            # ---- 读右轮传感器: 01 04 00 00 00 01 (1个寄存器=CH1) ----
            resp_right = _read_sensor(1, label="右")
            right_v, right_a = None, None
            if len(resp_right) >= 5 and resp_right[0] == SENSOR_ADDR and resp_right[1] == 0x04:
                ch1_raw = (resp_right[3] << 8) | resp_right[4]
                right_v = _raw_to_voltage(ch1_raw)
                right_a = _voltage_to_angle(right_v)

            # ---- 更新全局数据 ----
            with _angle_lock:
                if left_v is not None:
                    _left_voltage = left_v
                    _left_angle = left_a
                if right_v is not None:
                    _right_voltage = right_v
                    _right_angle = right_a
                # 兼容旧接口
                steer_voltage = _left_voltage
                steer_angle = _left_angle

            # if left_v is not None or right_v is not None:
                # logger.info(f"[角度] 左={_left_voltage:.3f}V/{_left_angle:.1f}°  右={_right_voltage:.3f}V/{_right_angle:.1f}°")

        except Exception as e:
            logger.error(f"角度读取异常: {e}")

        time.sleep(0.1)  # 100ms 读取一次


# ==================== 获取当前角度和电压 ====================
def get_steer_angle():
    """获取左轮转向角度（兼容旧接口）"""
    with _angle_lock:
        return steer_angle


def get_steer_voltage():
    """获取左轮传感器电压（兼容旧接口）"""
    with _angle_lock:
        return steer_voltage


def get_right_angle():
    """获取右轮转向角度"""
    with _angle_lock:
        return _right_angle


def get_sensor_data():
    """获取左右双传感器数据"""
    with _angle_lock:
        return {
            "left_voltage": round(_left_voltage, 3),
            "left_angle": round(_left_angle, 1),
            "right_voltage": round(_right_voltage, 3),
            "right_angle": round(_right_angle, 1),
        }


# ==================== 电机控制（FT-DM-01B Modbus）====================
def steer_motor_run(motor_id, speed, direction):
    """
    转向电机控制（内部函数）
    :param motor_id: 1(右转向) 或 2(左转向)
    :param speed: 0-100
    :param direction: 0=正转, 1=反转
    """
    global ser
    if ser is None or not ser.is_open:
        return False, "串口未初始化"

    if motor_id == 1:
        start_addr = 0x0004
    else:
        start_addr = 0x0009

    try:
        cmd = [
            DEVICE_ADDR, 0x10,
            (start_addr >> 8) & 0xFF, start_addr & 0xFF,
            0x00, 0x02,
            0x04,
            0x00, direction,
            0x00, speed
        ]
        crc_bytes = crc16_modbus(cmd)
        full_cmd = bytes(cmd) + crc_bytes
        with _motor_lock:
            ser.write(full_cmd)
        time.sleep(0.05)

        side = "右" if motor_id == 1 else "左"
        dir_text = "正转" if direction == 0 else "反转"
        logger.info(f"转向{side}轮 {dir_text} speed={speed} | {full_cmd.hex(' ').upper()}")
        return True, f"转向{side}轮指令已发送"

    except Exception as e:
        logger.error(f"转向电机控制失败：{e}", exc_info=True)
        return False, str(e)


def steer_motor_stop(motor_id):
    """停止指定转向电机"""
    return steer_motor_run(motor_id, speed=0, direction=0)


def steer_both_stop():
    """停止左右两个转向电机"""
    steer_motor_run(1, 0, 0)
    steer_motor_run(2, 0, 0)


# ==================== 闭环转向控制 ====================
def steer_to_angle(left_target, speed=50, timeout=10.0, right_target=None):
    """
    转向到目标角度（双线程独立闭环）
    每个轮子独立读传感器、独立判断、独立停止
    :param left_target: 左轮目标角度（度）
    :param speed: 转向速度 0-100
    :param timeout: 超时时间（秒）
    :param right_target: 右轮目标角度，None 则与左轮相同
    :return: (success, message)
    """
    global ser
    if ser is None or not ser.is_open:
        return False, "转向电机串口未初始化"

    if right_target is None:
        right_target = left_target

    speed = max(10, min(100, speed))

    # 读取当前左右角度
    left_cur = get_steer_angle()
    right_cur = get_right_angle()
    wait_end = time.time() + 2.0
    while time.time() < wait_end and (left_cur == 0.0 or right_cur == 0.0):
        if left_cur == 0.0:
            left_cur = get_steer_angle()
        if right_cur == 0.0:
            right_cur = get_right_angle()
        time.sleep(0.1)

    left_err = left_target - left_cur
    right_err = right_target - right_cur
    logger.info(f"开始转向：左={left_cur:.1f}°→{left_target}° 右={right_cur:.1f}°→{right_target}° 速={speed}%")

    # 发一次启动指令
    steer_motor_run(2, speed, 0 if left_err > 0 else 1)  # 左轮
    steer_motor_run(1, speed, 0 if right_err > 0 else 1)  # 右轮

    # ====== 双线程独立监测 ======
    def _monitor_wheel(motor_id, get_angle, target):
        """单个轮子的独立监测线程：读传感器→到位→停止本轮"""
        start = time.time()
        prev_error = None
        while time.time() - start < timeout:
            cur = get_angle()
            error = target - cur

            # 正常到位
            if abs(error) <= DEAD_ZONE:
                steer_motor_run(motor_id, 0, 0)  # 只停本轮
                logger.info(f"{'左' if motor_id==2 else '右'}轮到位：{cur:.1f}°")
                return

            # 过冲检测：误差符号反转 = 已在目标另一侧
            if prev_error is not None and error * prev_error < 0:
                steer_motor_run(motor_id, 0, 0)
                logger.info(f"{'左' if motor_id==2 else '右'}轮过冲停止：{cur:.1f}°")
                return

            prev_error = error
            time.sleep(0.1)
        # 超时，强制停止本轮
        steer_motor_run(motor_id, 0, 0)
        cur = get_angle()
        logger.warning(f"{'左' if motor_id==2 else '右'}轮超时：目标={target}° 当前={cur:.1f}°")

    t_left = threading.Thread(target=_monitor_wheel, args=(2, get_steer_angle, left_target))
    t_right = threading.Thread(target=_monitor_wheel, args=(1, get_right_angle, right_target))
    t_left.start()
    t_right.start()
    t_left.join()
    t_right.join()

    # 安全确保双轮停止
    steer_motor_run(1, 0, 0)
    steer_motor_run(2, 0, 0)
    left_final = get_steer_angle()
    right_final = get_right_angle()
    msg = f"转向完成：左={left_final:.1f}° 右={right_final:.1f}°"
    logger.info(msg)
    return True, msg


def steer_stop():
    """紧急停止转向"""
    steer_both_stop()
    logger.info("转向已紧急停止")
    return True, "转向已停止"


def steer_reset(timeout=5.0):
    """
    转向回零（回到 0° 位置）
    """
    return steer_to_angle(0.0, speed=50, timeout=timeout)
