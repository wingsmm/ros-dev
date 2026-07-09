#!/usr/bin/env python3
import rclpy
from rclpy.node import Node


# 自定义节点类（继承 Node）
class MyFirstNode(Node):
    def __init__(self):
        # 节点名：my_first_node（全局唯一）
        super().__init__("my_first_node")
        # 打印日志（ROS2 日志级别：info/warn/error/fatal/debug）
        self.get_logger().info("Hello ROS2 Node!")


def main(args=None):
    # 初始化 ROS2 上下文
    rclpy.init(args=args)
    # 创建节点实例
    node = MyFirstNode()
    # 保持节点运行（阻塞）
    rclpy.spin(node)
    # 销毁节点
    node.destroy_node()
    # 关闭 ROS2 上下文
    rclpy.shutdown()


if __name__ == "__main__":
    main()