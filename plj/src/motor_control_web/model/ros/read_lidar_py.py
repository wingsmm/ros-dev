#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import rospy
import sensor_msgs.point_cloud2 as pc2
from sensor_msgs.msg import PointCloud2

def print_cloud_all_info(msg):
    """打印点云的所有信息：元数据 + 所有点的详细数据"""
    # ====================== 第一步：打印点云元数据（整体信息）======================
    print("=" * 80)
    print("📋 点云元数据信息：")
    print(f"发布时间戳：{msg.header.stamp}")
    print(f"坐标系：{msg.header.frame_id}")
    print(f"点云宽度（一行点数）：{msg.width}")
    print(f"点云高度（行数）：{msg.height}")
    print(f"是否是有序点云：{'是' if msg.is_dense else '否'}")
    print(f"点云总点数：{msg.width * msg.height}")

    # 打印点云字段（每个点的维度）
    print("\n🔍 点云字段（每个点的维度）：")
    for field in msg.fields:
        print(f"  - 字段名：{field.name}，数据类型：{field.datatype}，偏移量：{field.offset}")

    # ====================== 第二步：打印前10个点（避免刷屏）=====================
    print("\n📊 点云数据（前10个点）：")
    all_points = pc2.read_points(msg, skip_nans=True)
    for idx, point in enumerate(all_points):
        if idx >= 10:
            break
        x = point[0] if len(point) >= 1 else 0.0
        y = point[1] if len(point) >= 2 else 0.0
        z = point[2] if len(point) >= 3 else 0.0
        intensity = point[3] if len(point) >= 4 else 0.0
        print(f"点{idx + 1}：x={x:.3f}  y={y:.3f}  z={z:.3f}  强度={intensity}")

    print("=" * 80 + "\n")

if __name__ == '__main__':
    # 初始化ROS节点
    rospy.init_node('print_all_lidar_data', anonymous=True)

    # ====================== 关键修改：读取正确节点的串口参数 ======================
    try:
        # 节点名改为 /unitree_lidar_ros_node
        lidar_port = rospy.get_param("/serial_unitree_lider")
        print(f"📌 雷达驱动当前打开的串口：{lidar_port}\n")
    except KeyError:
        print("⚠️  未找到雷达驱动的串口参数，请检查节点名是否正确\n")

    # 订阅点云话题（话题名不变，还是 /unilidar/cloud）
    topic_name = "/unilidar/cloud"
    rospy.Subscriber(topic_name, PointCloud2, print_cloud_all_info, queue_size=100)

    print(f"✅ 已启动，正在监听 {topic_name} 话题...")
    print("⚠️  仅打印前10个点，按 Ctrl+C 停止\n")

    rospy.spin()