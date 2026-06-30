"""
地面感知几何计算模块
实现 3D 空间 → 2D 像素投影，以及深度反投影

算法参考来源：
- depthimage_to_laserscan/DepthImageToLaserScan.h:169-211
  核心公式：X = (u - cx) * Z / fx

坐标系约定：
- base_link: 机器人底盘中心，x 向前，y 向左，z 向上
- camera_optical: 深度相机光心，z 向前，x 向右，y 向下（OpenCV 约定）
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from math import isfinite
from typing import List, Optional

from core.camera_ground_config import GroundPerceptionConfig


@dataclass
class Point3D:
    """3D 空间点（base_link 坐标系）"""
    x: float  # 向前（米）
    y: float  # 向左（米）
    z: float  # 向上（米）


@dataclass
class Point2D:
    """2D 像素点"""
    u: float  # 像素 x
    v: float  # 像素 y


class GroundPerceptionGeometry:
    """地面感知几何计算器"""

    def __init__(self, config: GroundPerceptionConfig) -> None:
        self.config = config

    def base_to_camera(self, p: Point3D) -> Point3D:
        """
        base_link 坐标系 → 相机光心坐标系转换

        外参：
        - CAMERA_X: base_link 向前 10cm
        - CAMERA_Z: base_link 向上 20cm
        - CAMERA_PITCH: 相机向下倾斜 0.35 弧度（约 20 度，正数）
        """
        # 平移：base_link → camera 安装位置
        x1 = p.x - self.config.camera_x
        y1 = p.y - self.config.camera_y
        z1 = p.z - self.config.camera_z

        # 旋转：绕 y 轴（左右方向）俯仰角
        # pitch 为正表示向下倾斜
        pitch = self.config.camera_pitch
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)

        # Positive pitch means the optical axis points down. In the base-aligned
        # x/z plane that is a negative rotation around y, so ground points stay
        # below the image horizon instead of drifting upward with range.
        x2 = x1 * cos_p + z1 * sin_p
        z2 = -x1 * sin_p + z1 * cos_p
        y2 = y1

        # 转换为相机光心坐标系（OpenCV 约定）：
        #   z: 向前（与 base_link x 同向）
        #   x: 向右（与 base_link -y 同向）
        #   y: 向下（与 base_link -z 同向）
        cam_z = x2  # base_link 前方 → 相机 z 轴正方向
        cam_x = -y2  # base_link 左 → 相机 x 轴负方向（即向右）
        cam_y = -z2  # base_link 上 → 相机 y 轴负方向（即向下）

        return Point3D(x=cam_x, y=cam_y, z=cam_z)

    def project_to_pixel(self, p_cam: Point3D, *, for_rgb: bool = False) -> Point2D:
        """
        相机坐标系 → 像素坐标系投影

        for_rgb=True 时使用 RGB 内参（灯带叠在 MJPEG 画面上）。
        """
        if p_cam.z <= 0:
            return Point2D(u=-1, v=-1)

        if for_rgb:
            fx = self.config.rgb_fx
            fy = self.config.rgb_fy
            cx = self.config.rgb_cx
            cy = self.config.rgb_cy
        else:
            fx = self.config.depth_fx
            fy = self.config.depth_fy
            cx = self.config.depth_cx
            cy = self.config.depth_cy

        u = cx + (p_cam.x * fx) / p_cam.z
        v = cy + (p_cam.y * fy) / p_cam.z
        return Point2D(u=u, v=v)

    def base_point_to_pixel_rgb(self, p_base: Point3D) -> Point2D:
        """base_link 点 → RGB 像素坐标"""
        return self.project_to_pixel(self.base_to_camera(p_base), for_rgb=True)

    def base_point_to_pixel(self, p_base: Point3D) -> Point2D:
        """base_link 点 → depth 像素坐标"""
        return self.project_to_pixel(self.base_to_camera(p_base), for_rgb=False)

    @staticmethod
    def _apply_ground_plane(p_cam: Point3D, ground_plane: object) -> Point3D:
        normal = getattr(ground_plane, "normal", None)
        offset = getattr(ground_plane, "offset", None)
        valid = bool(getattr(ground_plane, "valid", False))
        if not valid or normal is None or offset is None or len(normal) != 3:
            return p_cam
        nx, ny, nz = float(normal[0]), float(normal[1]), float(normal[2])
        if abs(ny) < 1e-6:
            return p_cam
        y = -(nx * p_cam.x + nz * p_cam.z + float(offset)) / ny
        return Point3D(x=p_cam.x, y=y, z=p_cam.z)

    def _base_point_to_pixel_rgb_on_ground(
        self, p_base: Point3D, ground_plane: Optional[object]
    ) -> Point2D:
        p_cam = self.base_to_camera(p_base)
        if ground_plane is not None:
            p_cam = self._apply_ground_plane(p_cam, ground_plane)
        return self.project_to_pixel(p_cam, for_rgb=True)

    def generate_corridor_polygon(
        self, ground_plane: Optional[object] = None
    ) -> List[Point2D]:
        """
        生成地面灯带的多边形顶点（像素坐标）

        灯带形状：沿 x 轴向前延伸的地面走廊。

        corridor_width_m 是真实物理宽度；1m、2m、5m 处仍然都是同一条
        0.24m 宽的 3D 地面走廊，只是在图像中按透视关系变窄。
        """
        half_w = self.config.corridor_width_m / 2.0
        near_d = max(0.05, min(self.config.overlay_near_range_m, self.config.overlay_max_range_m))
        max_d = max(
            self.config.overlay_max_range_m,
            self.config.obstacle_range_m,
            self.config.stair_range_m,
            near_d,
        )

        # 采样点数量（距离越远点越密，保证曲线平滑）
        num_points = 48
        points: List[Point2D] = []

        # 先画右边界（从近到远）
        for i in range(num_points):
            d = near_d + (i / (num_points - 1)) * (max_d - near_d)
            p = Point3D(x=d, y=-half_w, z=0.0)
            px = self._base_point_to_pixel_rgb_on_ground(p, ground_plane)
            if isfinite(px.u) and isfinite(px.v):
                points.append(px)

        for i in range(num_points - 1, -1, -1):
            d = near_d + (i / (num_points - 1)) * (max_d - near_d)
            p = Point3D(x=d, y=half_w, z=0.0)
            px = self._base_point_to_pixel_rgb_on_ground(p, ground_plane)
            if isfinite(px.u) and isfinite(px.v):
                points.append(px)

        return points

    def depth_pixel_to_3d(self, u: int, v: int, depth_mm: int) -> Point3D:
        """
        深度像素值 → base_link 3D 点（反投影）

        公式来源：DepthImageToLaserScan.h:198-199
            X = (u - cx) * depth * constant_x
            constant_x = unit_scaling / fx

        参数:
            u, v: 像素坐标
            depth_mm: 深度值（毫米，Astra Pro 原生格式）

        返回:
            base_link 坐标系下的 3D 点
        """
        if depth_mm <= 0:
            return Point3D(x=0, y=0, z=0)

        # 毫米 → 米
        z_cam = depth_mm * 0.001

        fx = self.config.depth_fx
        fy = self.config.depth_fy
        cx = self.config.depth_cx
        cy = self.config.depth_cy

        # 反投影到相机坐标系
        # 注意：相机光心坐标系是 z 向前，x 向右，y 向下
        x_cam = (u - cx) * z_cam / fx
        y_cam = (v - cy) * z_cam / fy

        # 相机坐标系 → base_link 坐标系（逆变换）
        # 先逆旋转，再逆平移
        pitch = self.config.camera_pitch
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)

        # x_cam 是相机 z（前方），y_cam 是相机 y（向下）
        # 相机坐标系下的点：(x_cam, y_cam, z_cam)
        # → base_link 旋转前的点：(z_cam, -x_cam, -y_cam)
        x_rot = z_cam
        y_rot = -x_cam
        z_rot = -y_cam

        # 逆俯仰旋转：base_to_camera 使用 -pitch，这里用 +pitch 还原。
        x1 = x_rot * cos_p - z_rot * sin_p
        z1 = x_rot * sin_p + z_rot * cos_p
        y1 = y_rot

        # 逆平移
        x_base = x1 + self.config.camera_x
        y_base = y1 + self.config.camera_y
        z_base = z1 + self.config.camera_z

        return Point3D(x=x_base, y=y_base, z=z_base)

    def is_in_roi(self, p: Point3D) -> bool:
        """判断点是否在检测 ROI 内（地面灯带区域）"""
        half_w = self.config.corridor_width_m / 2.0
        max_d = max(self.config.obstacle_range_m, self.config.stair_range_m)

        return (
            0 < p.x <= max_d
            and abs(p.y) <= half_w
            and p.z > -0.1  # 略低于地面也可能是噪点
        )
