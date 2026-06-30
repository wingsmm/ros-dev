"""Android prefs.xml / values-zh-rCN strings (verbatim for Qt settings UI)."""

from __future__ import annotations

# PreferenceScreen root
TOPIC_PREF_TITLE = "话题"
TOPIC_PREF_SUMMARY = "编辑默认话题名称"
WARNING_PREF_TITLE = "预警系统"
WARNING_PREF_SUMMARY = "编辑预警系统设置"
ADVANCED_CONTROLS_PREF_TITLE = "高级控制"
PREFS_ADVANCED_CONTROL_SETTINGS_SUMMARY = "编辑高级控制设置"

# Topic rows
JOY_PREF_TITLE = "摇杆话题"
LASER_PREF_TITLE = "激光扫描话题"
CAMERA_PREF_TITLE = "图像话题"
NAVSAT_PREF_TITLE = "GPS 话题"
ODOMETRY_PREF_TITLE = "里程计话题"
POSE_PREF_TITLE = "位姿话题"
MAP_TOPIC_PREF_TITLE = "地图话题"

JOY_PREF_SUMMARY = (
    "摇杆控件发布到此话题。\n期望消息类型：std_msgs/Twist\n当前值：%s"
)
LASER_PREF_SUMMARY = (
    "激光扫描控件订阅此话题。\n期望消息类型：sensor_msgs/LaserScan\n当前值：%s"
)
CAMERA_PREF_SUMMARY = (
    "摄像头控件订阅此话题。\n期望消息类型：sensor_msgs/CompressedImage\n当前值：%s"
)
ODOMETRY_PREF_SUMMARY = (
    "应用从此话题获取里程计数据。\n期望消息类型：nav_msgs/Odometry\n当前值：%s"
)
NAVSAT_PREF_SUMMARY = (
    "应用从此话题获取 GPS 数据。\n期望消息类型：navsat/fix\n当前值：%s"
)
POSE_PREF_SUMMARY = (
    "应用从此话题获取位姿信息。\n期望消息类型：geometry_msgs/Pose\n当前值：%s"
)
MAP_TOPIC_PREF_SUMMARY = (
    "SLAM 栅格地图话题。\n期望消息类型：nav_msgs/OccupancyGrid\n当前值：%s"
)

# SLAM bounds
SLAM_BOUNDS_PREF_TITLE = "SLAM 测试区域"
SLAM_BOUNDS_PREF_SUMMARY = "在 SLAM 地图上以黄色框显示的设定区域。"
SLAM_XMIN_PREF_TITLE = "SLAM X 最小值"
SLAM_XMAX_PREF_TITLE = "SLAM X 最大值"
SLAM_YMIN_PREF_TITLE = "SLAM Y 最小值"
SLAM_YMAX_PREF_TITLE = "SLAM Y 最大值"
SLAM_BOUND_PREF_SUMMARY = "设定的 SLAM 测试区域边界，单位米。\n当前值：%s"

# Warning
WARNING_ENABLE_PREF_TITLE = "启用预警系统"
WARNING_ENABLE_PREF_SUMMARY_OFF = "启用预警系统以检测即将发生的碰撞"
WARNING_ENABLE_PREF_SUMMARY_ON = "禁用预警系统"
WARNING_SAFEMODE_PREF_TITLE = "安全模式"
WARNING_SAFEMODE_PREF_SUMMARY_OFF = "启用以防止机器人撞墙"
WARNING_SAFEMODE_PREF_SUMMARY_ON = "禁用后允许机器人撞墙"
WARNING_BEEP_PREF_TITLE = "预警蜂鸣"
WARNING_BEEP_PREF_SUMMARY_OFF = "启用预警蜂鸣"
WARNING_BEEP_PREF_SUMMARY_ON = "禁用预警蜂鸣"
WARNING_MINDIST_PREF_TITLE = "预警距离"
WARNING_MINDIST_PREF_SUMMARY = "进入该距离后触发人工避障限速，单位米\n当前值：%s"
WARNING_FRONT_ANGLE_PREF_TITLE = "预警角度"
WARNING_FRONT_ANGLE_PREF_SUMMARY = "车体前方左右半角，单位度\n当前值：%s"

# Advanced
LASER_SCAN_DETAIL_PREF_TITLE = "激光扫描细节"
LASER_SCAN_DETAIL_PREF_SUMMARY = (
    "设置激光扫描可视化的细节级别。数值越大绘制的激光点越多\n当前值：%s"
)
RANDOM_WALK_RANGE_MINIMUM_PREF_TITLE = "随机游走最小距离"
RANDOM_WALK_RANGE_MINIMUM_PREF_SUMMARY = (
    "随机游走算法在感知到此距离时停止并转向\n当前值：%s"
)
REVERSE_ANGLE_READING_TITLE = "反转激光扫描"
REVERSE_ANGLE_READING_SUMMARY_OFF = "反转角度读数（最小→最大角）"
REVERSE_ANGLE_READING_SUMMARY_ON = "反转角度读数（最大→最小角）"
INVERT_X_AXIS_TITLE = "反转 X 轴"
INVERT_X_AXIS_SUMMARY = "反转 X 轴驱动方向"
INVERT_Y_AXIS_TITLE = "反转 Y 轴"
INVERT_Y_AXIS_SUMMARY = "反转 Y 轴驱动方向"
INVERT_ANGULAR_VELOCITY_TITLE = "反转角速度"
INVERT_ANGULAR_VELOCITY_SUMMARY = "反转角速度驱动方向"
MANUAL_LINEAR_SPEED_PREF_TITLE = "人工按钮线速度"
MANUAL_ANGULAR_SPEED_PREF_TITLE = "人工按钮角速度"
MANUAL_LINEAR_SPEED_PREF_SUMMARY = (
    "按住按钮与 SLAM 导航共用的线速度（m/s，0.03–0.30）\n当前值：%s"
)
MANUAL_ANGULAR_SPEED_PREF_SUMMARY = (
    "按住按钮与 SLAM 导航共用的角速度（rad/s，0.05–0.80）\n当前值：%s"
)

# Dialog buttons
CANCEL = "取消"
OK = "确定"

TOPIC_SUMMARY_BY_KEY = {
    "joystick_topic": JOY_PREF_SUMMARY,
    "laser_topic": LASER_PREF_SUMMARY,
    "camera_topic": CAMERA_PREF_SUMMARY,
    "navsat_topic": NAVSAT_PREF_SUMMARY,
    "odometry_topic": ODOMETRY_PREF_SUMMARY,
    "pose_topic": POSE_PREF_SUMMARY,
    "map_topic": MAP_TOPIC_PREF_SUMMARY,
}

TOPIC_TITLE_BY_KEY = {
    "joystick_topic": JOY_PREF_TITLE,
    "laser_topic": LASER_PREF_TITLE,
    "camera_topic": CAMERA_PREF_TITLE,
    "navsat_topic": NAVSAT_PREF_TITLE,
    "odometry_topic": ODOMETRY_PREF_TITLE,
    "pose_topic": POSE_PREF_TITLE,
    "map_topic": MAP_TOPIC_PREF_TITLE,
}
