"""
车身水平自动调整 - 倾角传感器结合前后升降电机
多线程监控X角度，动态调整前后电机速度以保持水平。
"""
import threading
import time

from tool.log_config import logger
from model.rear_lift import lift_speed_run
from model.front_grab import grab_speed_run
from model.tilt_sensor import read_x_angle

# 运行状态
_running = False
_thread = None
_current_lift_speed = 0
_current_grab_speed = 0

# 控制参数
ANGLE_THRESHOLD = 1.0       # 角度死区阈值(°)，小于此值认为已水平
SPEED_STEP = 50             # 每次调整降速步长
CHECK_INTERVAL = 0.3        # 检测间隔(秒)
MIN_SPEED = 150              # 最低速度，低于此值直接停止


def _monitor_loop(lift_init, grab_init):
    global _running, _current_lift_speed, _current_grab_speed
    lift_spd = abs(lift_init)
    grab_spd = abs(grab_init)
    lift_dir = 1 if lift_init >= 0 else -1
    grab_dir = 1 if grab_init >= 0 else -1
    _current_lift_speed = lift_spd
    _current_grab_speed = grab_spd

    # 启动电机
    lift_speed_run(lift_init)
    grab_speed_run(grab_init)
    logger.info(f"水平调整开始: 升降={lift_init}, 扒手={grab_init}")

    while _running:
        time.sleep(CHECK_INTERVAL)
        if not _running:
            break

        # 读取角度
        angle, _ = read_x_angle()
        if angle is None:
            logger.warning("水平调整: 倾角传感器读取失败，跳过本次检测")
            continue

        logger.info(f"水平调整: 角度={angle:.2f}°, 升降速度={_current_lift_speed}, 扒手速度={_current_grab_speed}")

        # 判断是否已水平，水平则维持当前速度继续运行
        if abs(angle) <= ANGLE_THRESHOLD:
            continue

        if angle < -ANGLE_THRESHOLD:
            # 车身前倾 → 后侧升降(支腿)太快 → 降后侧速度
            _current_lift_speed = max(0, _current_lift_speed - SPEED_STEP)
            if _current_lift_speed <= MIN_SPEED:
                _current_lift_speed = 0
            new_speed = _current_lift_speed * lift_dir
            lift_speed_run(new_speed)
            logger.info(f"水平调整: 前倾({angle:.1f}°), 后侧降速→{new_speed}")

        elif angle > ANGLE_THRESHOLD:
            # 车身后倾 → 前侧扒手太快 → 降前侧速度
            _current_grab_speed = max(0, _current_grab_speed - SPEED_STEP)
            if _current_grab_speed <= MIN_SPEED:
                _current_grab_speed = 0
            new_speed = _current_grab_speed * grab_dir
            grab_speed_run(new_speed)
            logger.info(f"水平调整: 后倾({angle:.1f}°), 前侧降速→{new_speed}")

    # 用户手动停止后，停止电机
    lift_speed_run(0)
    grab_speed_run(0)
    _current_lift_speed = 0
    _current_grab_speed = 0
    logger.info("水平调整结束")


def start_leveling(lift_speed, grab_speed):
    """
    启动水平自动调整
    :param lift_speed: 后侧升降初始速度（有符号）
    :param grab_speed: 前侧扒手初始速度（有符号）
    :return: (success, message)
    """
    global _running, _thread
    if _running:
        return False, "水平调整已在运行中"
    _running = True
    _thread = threading.Thread(target=_monitor_loop, args=(lift_speed, grab_speed), daemon=True)
    _thread.start()
    return True, f"水平调整已启动: 升降={lift_speed}, 扒手={grab_speed}"


def stop_leveling():
    """停止水平自动调整"""
    global _running
    if not _running:
        return False, "水平调整未运行"
    _running = False
    lift_speed_run(0)
    grab_speed_run(0)
    return True, "水平调整已停止"


def is_leveling():
    """查询是否正在运行"""
    return _running
