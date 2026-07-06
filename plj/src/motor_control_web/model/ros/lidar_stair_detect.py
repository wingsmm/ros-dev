# 检测楼梯程序
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import rospy
import math
import numpy as np
from collections import defaultdict
import sensor_msgs.point_cloud2 as pc2
from sensor_msgs.msg import PointCloud2

# ===================== 可自行调参 =====================
# 检测区域范围
RANGE_FRONT_MIN = 1.0       # 最小前方距离(m)
RANGE_FRONT_MAX = 6.0       # 最大前方距离(m)
RANGE_Y_MIN = -1.0          # 左右左边界(m)
RANGE_Y_MAX = 1.0           # 左右右边界(m)
RANGE_Z_MIN = 0.1           # 最低离地高度(m)
RANGE_Z_MAX = 1.5          # 最高离地高度(m)

# 楼梯参数
STEP_H_MIN = 0.10           # 台阶最小高度(m)
STEP_H_MAX = 0.18           # 台阶最大高度(m)
CLUSTER_Z_TOL = 0.05        # 高度聚类容差(m)
MIN_POINTS_PER_CLUSTER = 40 # 每级台阶最少点数
MIN_STAIR_LEVEL = 2         # 至少2级台阶才算楼梯
# =====================================================

def transform_point(x, y, z):
    """
    适配：L1 雷达 朝前竖装 前脸安装
    原始点云 -> 机器人标准坐标系矫正
    fx: 正前方距离
    fy: 左右
    fz: 真实离地高度
    """
    fx = z
    fy = y
    fz = -x
    return fx, fy, fz

def preprocess_cloud(cloud_msg):
    """点云预处理：坐标矫正 + 范围滤波"""
    valid_points = []
    for p in pc2.read_points(cloud_msg, skip_nans=True):
        x, y, z = p[0], p[1], p[2]
        fx, fy, fz = transform_point(x, y, z)

        # 空间范围过滤
        if (RANGE_FRONT_MIN < fx < RANGE_FRONT_MAX and
            RANGE_Y_MIN < fy < RANGE_Y_MAX and
            RANGE_Z_MIN < fz < RANGE_Z_MAX):
            valid_points.append([fx, fy, fz])
    return np.array(valid_points)

def cluster_by_height(points):
    """按离地高度fz聚类，分出每一级台阶"""
    clusters = defaultdict(list)
    if len(points) == 0:
        return clusters

    # 按高度排序
    sorted_idx = np.argsort(points[:, 2])
    points_sorted = points[sorted_idx]

    curr_z = points_sorted[0][2]
    clusters[curr_z].append(points_sorted[0])

    for pt in points_sorted[1:]:
        z = pt[2]
        if abs(z - curr_z) < CLUSTER_Z_TOL:
            clusters[curr_z].append(pt)
        else:
            curr_z = z
            clusters[curr_z].append(pt)

    # 过滤点数太少的噪声簇
    filter_clusters = {}
    for z_key, pts in clusters.items():
        if len(pts) >= MIN_POINTS_PER_CLUSTER:
            avg_z = np.mean([p[2] for p in pts])
            avg_x = np.mean([p[0] for p in pts])
            filter_clusters[avg_z] = {"points": pts, "avg_x": avg_x}
    return filter_clusters

def is_staircase(clusters):
    """判断是否为楼梯"""
    z_list = sorted(list(clusters.keys()))
    if len(z_list) < MIN_STAIR_LEVEL:
        return False, 0, []

    # 检查相邻台阶高度差是否合规
    valid_cnt = 0
    step_gaps = []
    for i in range(1, len(z_list)):
        gap = z_list[i] - z_list[i-1]
        step_gaps.append(gap)
        if STEP_H_MIN <= gap <= STEP_H_MAX:
            valid_cnt += 1

    # 高度差达标比例
    if valid_cnt / (len(z_list)-1) < 0.8:
        return False, len(z_list), z_list

    # 检查台阶是否逐级往前变远
    x_list = [clusters[z]["avg_x"] for z in z_list]
    is_forward_increase = all(x_list[i] < x_list[i+1] for i in range(len(x_list)-1))

    if not is_forward_increase:
        return False, len(z_list), z_list

    return True, len(z_list), z_list

def cloud_callback(msg):
    pts = preprocess_cloud(msg)
    if len(pts) < MIN_POINTS_PER_CLUSTER * MIN_STAIR_LEVEL:
        return

    clusters = cluster_by_height(pts)
    stair_flag, level_num, z_heights = is_staircase(clusters)

    print("=" * 60)
    if stair_flag:
        avg_dist = np.mean([clusters[z]["avg_x"] for z in z_heights])
        print("✅ 检测到楼梯！")
        print(f"🔹 距离机器人：{avg_dist:.2f} m")
        print(f"🔹 台阶层数：{level_num} 级")
        print(f"🔹 各层高度：{[round(h,2) for h in z_heights]} m")
    else:
        print("❌ 未检测到标准楼梯")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    rospy.init_node("lidar_stair_detection_front_mount", anonymous=True)
    rospy.Subscriber("/unilidar/cloud", PointCloud2, cloud_callback, queue_size=10)
    print("✅ 楼梯识别节点已启动，监听 /unilidar/cloud ...")
    print("🔧 参数可在代码顶部自行调整\n")
    rospy.spin()