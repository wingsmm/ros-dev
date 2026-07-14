#include <chrono>
#include <cmath>
#include <memory>
#include <string>

#include "geometry_msgs/msg/pose_stamped.hpp"
#include "geometry_msgs/msg/transform_stamped.hpp"
#include "lio_odom_adapter/transform_math.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "nav_msgs/msg/path.hpp"
#include "rclcpp/rclcpp.hpp"
#include "tf2/LinearMath/Quaternion.h"
#include "tf2_ros/buffer.h"
#include "tf2_ros/transform_broadcaster.h"
#include "tf2_ros/transform_listener.h"
#include "tf2_ros/static_transform_broadcaster.h"

using namespace std::chrono_literals;

namespace lio_odom_adapter
{

class LioOdomAdapterNode : public rclcpp::Node
{
public:
  LioOdomAdapterNode()
  : Node("lio_odom_adapter")
  {
    input_topic_ = declare_parameter<std::string>("input_odom_topic", "/aft_mapped_to_init");
    output_odom_topic_ = declare_parameter<std::string>("output_odom_topic", "/odom");
    output_path_topic_ = declare_parameter<std::string>("output_path_topic", "/odom_path");
    odom_frame_ = declare_parameter<std::string>("odom_frame", "odom");
    base_frame_ = declare_parameter<std::string>("base_frame", "base_link");
    imu_frame_ = declare_parameter<std::string>("imu_frame", "unilidar_imu");
    camera_init_frame_ = declare_parameter<std::string>("camera_init_frame", "camera_init");
    max_path_length_ = declare_parameter<int>("max_path_length", 1000);
    tf_lookup_timeout_sec_ = declare_parameter<double>("tf_lookup_timeout_sec", 0.05);
    warn_period_sec_ = declare_parameter<double>("tf_warn_period_sec", 2.0);

    if (max_path_length_ < 1) {
      max_path_length_ = 1;
    }

    tf_buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
    tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);
    tf_broadcaster_ = std::make_unique<tf2_ros::TransformBroadcaster>(*this);
    static_broadcaster_ = std::make_unique<tf2_ros::StaticTransformBroadcaster>(*this);

    publish_static_odom_camera_init();

    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>(output_odom_topic_, 10);
    path_pub_ = create_publisher<nav_msgs::msg::Path>(output_path_topic_, 10);
    path_msg_.header.frame_id = odom_frame_;

    sub_ = create_subscription<nav_msgs::msg::Odometry>(
      input_topic_, rclcpp::SensorDataQoS(),
      std::bind(&LioOdomAdapterNode::on_odom, this, std::placeholders::_1));

    RCLCPP_INFO(
      get_logger(),
      "lio_odom_adapter: %s -> %s / %s, TF %s->%s (via %s)",
      input_topic_.c_str(), output_odom_topic_.c_str(), output_path_topic_.c_str(),
      odom_frame_.c_str(), base_frame_.c_str(), imu_frame_.c_str());
  }

private:
  void publish_static_odom_camera_init()
  {
    geometry_msgs::msg::TransformStamped tf;
    tf.header.stamp = now();
    tf.header.frame_id = odom_frame_;
    tf.child_frame_id = camera_init_frame_;
    tf.transform.translation.x = 0.0;
    tf.transform.translation.y = 0.0;
    tf.transform.translation.z = 0.0;
    tf.transform.rotation.x = 0.0;
    tf.transform.rotation.y = 0.0;
    tf.transform.rotation.z = 0.0;
    tf.transform.rotation.w = 1.0;
    static_broadcaster_->sendTransform(tf);
  }

  static bool pose_finite(const geometry_msgs::msg::Pose & pose)
  {
    return std::isfinite(pose.position.x) && std::isfinite(pose.position.y) &&
           std::isfinite(pose.position.z) &&
           std::isfinite(pose.orientation.x) && std::isfinite(pose.orientation.y) &&
           std::isfinite(pose.orientation.z) && std::isfinite(pose.orientation.w);
  }

  static Rigid3 from_msg(const geometry_msgs::msg::Pose & pose)
  {
    return {
      Vec3{pose.position.x, pose.position.y, pose.position.z},
      Quat{
        pose.orientation.x, pose.orientation.y, pose.orientation.z,
        pose.orientation.w}};
  }

  static Rigid3 from_tf(const geometry_msgs::msg::Transform & t)
  {
    return {
      Vec3{t.translation.x, t.translation.y, t.translation.z},
      Quat{t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w}};
  }

  static void to_pose(const Rigid3 & t, geometry_msgs::msg::Pose & pose)
  {
    pose.position.x = t.translation.x;
    pose.position.y = t.translation.y;
    pose.position.z = t.translation.z;
    pose.orientation.x = t.rotation.x;
    pose.orientation.y = t.rotation.y;
    pose.orientation.z = t.rotation.z;
    pose.orientation.w = t.rotation.w;
  }

  void maybe_warn_tf(const std::string & reason)
  {
    const auto now_t = now();
    if ((now_t - last_tf_warn_).seconds() < warn_period_sec_) {
      return;
    }
    last_tf_warn_ = now_t;
    RCLCPP_WARN(get_logger(), "TF not ready, skip odom publish: %s", reason.c_str());
  }

  void on_odom(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    if (!pose_finite(msg->pose.pose)) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000, "reject NaN/Inf pose on %s", input_topic_.c_str());
      return;
    }

    geometry_msgs::msg::TransformStamped tf_base_imu;
    try {
      tf_base_imu = tf_buffer_->lookupTransform(
        base_frame_, imu_frame_, msg->header.stamp,
        rclcpp::Duration::from_seconds(tf_lookup_timeout_sec_));
    } catch (const tf2::TransformException & ex) {
      try {
        tf_base_imu = tf_buffer_->lookupTransform(
          base_frame_, imu_frame_, tf2::TimePointZero);
      } catch (const tf2::TransformException & ex2) {
        maybe_warn_tf(ex2.what());
        return;
      }
      (void)ex;
    }

    Rigid3 t_camera_init_imu = from_msg(msg->pose.pose);
    Rigid3 t_base_imu = from_tf(tf_base_imu.transform);
    Rigid3 t_odom_base = odom_base_from_imu(t_camera_init_imu, t_base_imu);

    Twist6 twist_imu{
      Vec3{
        msg->twist.twist.linear.x, msg->twist.twist.linear.y,
        msg->twist.twist.linear.z},
      Vec3{
        msg->twist.twist.angular.x, msg->twist.twist.angular.y,
        msg->twist.twist.angular.z}};
    Twist6 twist_base = transform_twist_imu_to_base(twist_imu, t_base_imu);

    Cov6 cov_pose{};
    Cov6 cov_twist{};
    for (size_t i = 0; i < 36; ++i) {
      cov_pose[i] = msg->pose.covariance[i];
      cov_twist[i] = msg->twist.covariance[i];
    }
    Cov6 cov_pose_base = transform_covariance_imu_to_base(cov_pose, t_base_imu);
    Cov6 cov_twist_base = transform_covariance_imu_to_base(cov_twist, t_base_imu);

    nav_msgs::msg::Odometry out;
    out.header.stamp = msg->header.stamp;
    out.header.frame_id = odom_frame_;
    out.child_frame_id = base_frame_;
    to_pose(t_odom_base, out.pose.pose);
    out.twist.twist.linear.x = twist_base.linear.x;
    out.twist.twist.linear.y = twist_base.linear.y;
    out.twist.twist.linear.z = twist_base.linear.z;
    out.twist.twist.angular.x = twist_base.angular.x;
    out.twist.twist.angular.y = twist_base.angular.y;
    out.twist.twist.angular.z = twist_base.angular.z;
    for (size_t i = 0; i < 36; ++i) {
      out.pose.covariance[i] = cov_pose_base[i];
      out.twist.covariance[i] = cov_twist_base[i];
    }
    odom_pub_->publish(out);

    geometry_msgs::msg::TransformStamped tf_out;
    tf_out.header.stamp = msg->header.stamp;
    tf_out.header.frame_id = odom_frame_;
    tf_out.child_frame_id = base_frame_;
    tf_out.transform.translation.x = t_odom_base.translation.x;
    tf_out.transform.translation.y = t_odom_base.translation.y;
    tf_out.transform.translation.z = t_odom_base.translation.z;
    tf_out.transform.rotation.x = t_odom_base.rotation.x;
    tf_out.transform.rotation.y = t_odom_base.rotation.y;
    tf_out.transform.rotation.z = t_odom_base.rotation.z;
    tf_out.transform.rotation.w = t_odom_base.rotation.w;
    tf_broadcaster_->sendTransform(tf_out);

    geometry_msgs::msg::PoseStamped ps;
    ps.header = out.header;
    ps.pose = out.pose.pose;
    path_msg_.header.stamp = out.header.stamp;
    path_msg_.header.frame_id = odom_frame_;
    path_msg_.poses.push_back(ps);
    while (static_cast<int>(path_msg_.poses.size()) > max_path_length_) {
      path_msg_.poses.erase(path_msg_.poses.begin());
    }
    path_pub_->publish(path_msg_);
  }

  std::string input_topic_;
  std::string output_odom_topic_;
  std::string output_path_topic_;
  std::string odom_frame_;
  std::string base_frame_;
  std::string imu_frame_;
  std::string camera_init_frame_;
  int max_path_length_{1000};
  double tf_lookup_timeout_sec_{0.05};
  double warn_period_sec_{2.0};

  std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
  std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
  std::unique_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
  std::unique_ptr<tf2_ros::StaticTransformBroadcaster> static_broadcaster_;

  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr sub_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_pub_;
  nav_msgs::msg::Path path_msg_;
  rclcpp::Time last_tf_warn_{0, 0, RCL_ROS_TIME};
};

}  // namespace lio_odom_adapter

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<lio_odom_adapter::LioOdomAdapterNode>());
  rclcpp::shutdown();
  return 0;
}
