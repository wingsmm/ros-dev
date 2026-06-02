import logging
import os
from datetime import datetime


def setup_logger(log_dir="log", log_level=logging.INFO):
    """
    配置日志记录器，日志文件固定放在项目的log目录下
    参数：
        log_dir: 日志目录名（默认log，可自定义）
        log_level: 日志级别（默认INFO）
    返回：
        配置好的logger对象
    """
    # 1. 确保log目录存在（不存在则自动创建）
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 2. 生成日志文件名（log目录下按日期命名）
    today = datetime.now().strftime("%Y%m%d")
    log_file_name = os.path.join(log_dir, f"motor_log_{today}.log")

    # 3. 创建日志器并清空原有处理器（避免重复输出）
    logger = logging.getLogger("MotorControl")
    logger.setLevel(log_level)
    logger.handlers.clear()

    # 4. 定义详细的日志格式（包含时间、级别、模块、行号等）
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 5. 配置文件处理器（写入log目录下的日志文件）
    file_handler = logging.FileHandler(log_file_name, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 6. 配置控制台处理器（同时输出到控制台）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 记录日志目录信息，方便调试
    logger.info(f"日志文件已配置，存储路径：{os.path.abspath(log_file_name)}")
    return logger


# 初始化全局日志器（项目启动时执行一次）
logger = setup_logger()

# ===================== 测试示例 =====================
if __name__ == "__main__":
    # 测试日志输出
    logger.debug("调试信息：串口参数初始化完成")
    logger.info("正常信息：电机限位读取成功")
    logger.warning("警告信息：串口超时时间使用默认值")
    logger.error("错误信息：无法连接到COM5串口")
    logger.critical("严重错误：限位触发，电机紧急停止")