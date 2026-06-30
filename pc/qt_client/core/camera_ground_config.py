"""
地面感知配置模块
从 os.environ 读取配置，与 DepthSourceConfig 风格一致

参考来源：
- xtark_nav_depthcamera/config/depth_cam.yaml (内参)
- xtark_nav_depthcamera/config/diff/costmap_common_params.yaml (车体宽度)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _env_float(key: str, default: float) -> float:
    """读取 float 类型环境变量"""
    value = os.environ.get(key, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    """读取 int 类型环境变量"""
    value = os.environ.get(key, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    """读取 bool 类型环境变量"""
    value = os.environ.get(key, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


@dataclass
class GroundPerceptionConfig:
    """地面感知配置容器"""

    # 总开关
    enabled: bool

    # Overlay 绘制方法: "trapezoid" (硬编码梯形, 默认) 或 "geometric" (几何投影)
    overlay_method: str

    # 核心参数（a/b/c）
    corridor_width_m: float  # a: 车体宽度（米）
    obstacle_range_m: float  # b: 障碍检测距离（米）
    stair_range_m: float  # c: 楼梯检测距离（米）

    # 显示参数
    overlay_max_range_m: float  # 灯带最大延伸距离
    overlay_near_range_m: float  # 灯带近端距离，避免从相机正下方开始投影
    max_fps: int  # 算法帧率限制

    # 梯形方法参数（仅 overlay_method="trapezoid" 时使用）
    trapezoid_bottom_y_ratio: float  # 梯形底边离图像底部的偏移比例
    trapezoid_top_y_ratio: float  # 梯形顶边位置（图像高度比例）
    trapezoid_top_width_ratio: float  # 梯形顶边宽度比例（相对于图像宽度）

    # 深度相机内参（Astra Pro 真实标定数据，用于 depth 反投影）
    depth_fx: float
    depth_fy: float
    depth_cx: float
    depth_cy: float

    # RGB 内参（UVC / MJPEG 预览，用于灯带 overlay 投影）
    rgb_fx: float
    rgb_fy: float
    rgb_cx: float
    rgb_cy: float
    rgb_ref_width: int
    rgb_ref_height: int

    # base_link -> camera_link 外参
    camera_x: float  # 前后偏移（米，车头向前为正）
    camera_y: float  # 左右偏移（米）
    camera_z: float  # 高度偏移（米，向上为正）
    camera_pitch: float  # 俯仰角（弧度，向下倾斜为正）

    @classmethod
    def from_env(cls) -> "GroundPerceptionConfig":
        """从环境变量读取配置"""
        method = os.environ.get("GROUND_OVERLAY_METHOD", "trapezoid").strip().lower()
        if method not in ("geometric", "trapezoid"):
            logger.warning(
                "unknown GROUND_OVERLAY_METHOD '%s', fallback to 'trapezoid'",
                method,
            )
            method = "trapezoid"

        return cls(
            enabled=_env_bool("GROUND_OVERLAY_ENABLE", True),
            overlay_method=method,
            corridor_width_m=_env_float("GROUND_CORRIDOR_WIDTH_M", 0.24),
            obstacle_range_m=_env_float("GROUND_OBSTACLE_RANGE_M", 2.0),
            stair_range_m=_env_float("GROUND_STAIR_RANGE_M", 2.5),
            overlay_max_range_m=_env_float("GROUND_OVERLAY_MAX_RANGE_M", 5.0),
            overlay_near_range_m=_env_float("GROUND_OVERLAY_NEAR_RANGE_M", 0.35),
            max_fps=_env_int("GROUND_PERCEPTION_MAX_FPS", 5),
            trapezoid_bottom_y_ratio=_env_float("GROUND_TRAPEZOID_BOTTOM_Y_RATIO", 0.02),
            trapezoid_top_y_ratio=_env_float("GROUND_TRAPEZOID_TOP_Y_RATIO", 0.4),
            trapezoid_top_width_ratio=_env_float("GROUND_TRAPEZOID_TOP_WIDTH_RATIO", 0.4),
            depth_fx=_env_float("DEPTH_FX", 578.579),
            depth_fy=_env_float("DEPTH_FY", 579.358),
            depth_cx=_env_float("DEPTH_CX", 679.157),
            depth_cy=_env_float("DEPTH_CY", 323.147),
            rgb_fx=_env_float("RGB_FX", 520.0),
            rgb_fy=_env_float("RGB_FY", 520.0),
            rgb_cx=_env_float("RGB_CX", 320.0),
            rgb_cy=_env_float("RGB_CY", 240.0),
            rgb_ref_width=_env_int("RGB_REF_WIDTH", 640),
            rgb_ref_height=_env_int("RGB_REF_HEIGHT", 480),
            camera_x=_env_float("CAMERA_X", 0.10),
            camera_y=_env_float("CAMERA_Y", 0.0),
            camera_z=_env_float("CAMERA_Z", 0.20),
            camera_pitch=_env_float("CAMERA_PITCH", 0.35),
        )

    def log_summary(self) -> None:
        """启动时打印一次配置，便于对照 .env 与标定。"""
        logger.info(
            "ground config: enabled=%s method=%s a=%.2fm b=%.1fm c=%.1fm overlay_range=%.1fm "
            "overlay_near=%.2fm max_fps=%d trapezoid=(bottom_y=%.2f top_y=%.2f top_w=%.2f) "
            "pitch=%.3f cam=(%.2f,%.2f,%.2f) "
            "depth_K=(fx=%.1f,fy=%.1f,cx=%.1f,cy=%.1f) "
            "rgb_K=(fx=%.1f,fy=%.1f,cx=%.1f,cy=%.1f) ref=%dx%d",
            self.enabled,
            self.overlay_method,
            self.corridor_width_m,
            self.obstacle_range_m,
            self.stair_range_m,
            self.overlay_max_range_m,
            self.overlay_near_range_m,
            self.max_fps,
            self.trapezoid_bottom_y_ratio,
            self.trapezoid_top_y_ratio,
            self.trapezoid_top_width_ratio,
            self.camera_pitch,
            self.camera_x,
            self.camera_y,
            self.camera_z,
            self.depth_fx,
            self.depth_fy,
            self.depth_cx,
            self.depth_cy,
            self.rgb_fx,
            self.rgb_fy,
            self.rgb_cx,
            self.rgb_cy,
            self.rgb_ref_width,
            self.rgb_ref_height,
        )
