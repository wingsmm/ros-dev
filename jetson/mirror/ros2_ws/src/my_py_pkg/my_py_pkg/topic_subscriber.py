#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

# 订阅者节点
class TopicSubscriber(Node):
    def __init__(self):
        super().__init__("topic_subscriber_node")
        # 创建订阅者：订阅话题「chatter」，收到消息执行 callback
        self.subscription_ = self.create_subscription(
            String,
            "chatter",
            self.listener_callback,  # 回调函数
            10  # 队列大小
        )

    def listener_callback(self, msg):
        # 接收消息并打印
        self.get_logger().info(f"Received: {msg.data}")


def main(args=None):
    rclpy.init(args=args)
    node = TopicSubscriber()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()