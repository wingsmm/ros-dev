#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
# 导入消息类型（字符串类型，ROS2 内置）
from std_msgs.msg import String

# 发布者节点
class TopicPublisher(Node):
    def __init__(self):
        super().__init__("topic_publisher_node")
        # 创建发布者：话题名「chatter」，消息类型 String，队列大小 10
        self.publisher_ = self.create_publisher(String, "chatter", 10)
        # 创建定时器（每 1 秒执行一次 callback）
        self.timer_ = self.create_timer(1.0, self.timer_callback)
        self.count_ = 0  # 计数变量

    def timer_callback(self):
        # 构造消息
        msg = String()
        msg.data = f"Hello ROS2! Count: {self.count_}"
        # 发布消息
        self.publisher_.publish(msg)
        self.get_logger().info(f"Published: {msg.data}")
        self.count_ += 1


def main(args=None):
    # 初始化 ROS2 上下文
    rclpy.init(args=args)
    # 创建节点实例
    node = TopicPublisher()
    # 保持节点运行（阻塞）
    rclpy.spin(node)
    # 销毁节点
    node.destroy_node()
    # 关闭 ROS2 上下文
    rclpy.shutdown()
    #配置完功能包才能运行这个文件（怎么配置，请查看终极文档）

if __name__ == "__main__":
    main()