// l1_cloud_align_node
//
// Subscribe: /unilidar/cloud  (sensor_msgs/PointCloud2, frame=unilidar_lidar)
// Publish : /unilidar/cloud_aligned (sensor_msgs/PointCloud2, frame=base_link)
//
// Applies a rigid-body rotation plus translation to every point's (x, y, z).
// All other point fields are kept byte-for-byte. NaN or Inf points pass
// through unchanged.
//
// Parameters (ros2 parameter server, can be updated at runtime):
//   input_topic  (string)      default /unilidar/cloud
//   output_topic (string)      default /unilidar/cloud_aligned
//   target_frame (string)      default base_link
//   xyz          (double[3])   default [0, 0, 0]
//   base_rpy_rad (double[3])   default [0, 0, 0]   安装基准，不由 UI 改
//   trim_rpy_rad (double[3])   default [0, 0, 0]   现场微调，UI 改这个
//
// Mounting baseline used by this project:
//   lidar +Z -> base_link +X  (车头)
//   lidar +X -> base_link +Z  (朝上)
//   lidar +Y -> base_link -Y  (车右)
//
// That baseline is encoded as:
//   base_rpy_rad = [pi, -pi/2, 0]
//
// Do not "flatten" the scene by changing base_rpy_rad. It is the physical
// mounting transform from the L1 sensor frame to the robot base frame.
//
// Rotation composition:
//   R_base_lidar = R(base_rpy_rad)     lidar frame -> base_link (安装基准)
//   R_trim_base  = R(trim_rpy_rad)     base_link 车体系里的现场微调
//   R_final      = R_trim_base * R_base_lidar
//   p_out        = R_final * p_in + xyz
//
// UI only exposes trim_rpy_rad. It is intentionally user-facing:
//   roll  = 左右歪/侧倾，绕 base_link +X 调；现场已验证主要靠它调平楼顶/地面
//   pitch = 前后翘，绕 base_link +Y 调
//   yaw   = 车头方向偏，绕 base_link +Z 调
//
// In other words, the user rotates the already-mounted point cloud in the
// robot frame, not around the raw L1 axes and not by moving RViz/TF axes.
//
// The YAML config (~/qt/ros2_ws/src/l1_cloud_align/config/l1_cloud_align.yaml)
// is the source of truth. To apply new extrinsics, cockpit rewrites the YAML
// and restarts this node — no live parameter reload is required.

#include <array>
#include <cmath>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>

namespace l1_cloud_align
{

struct Rotation
{
  std::array<double, 9> r{{1, 0, 0, 0, 1, 0, 0, 0, 1}};

  void set_from_rpy(double roll, double pitch, double yaw)
  {
    const double cr = std::cos(roll);
    const double sr = std::sin(roll);
    const double cp = std::cos(pitch);
    const double sp = std::sin(pitch);
    const double cy = std::cos(yaw);
    const double sy = std::sin(yaw);

    // R = Rz(yaw) * Ry(pitch) * Rx(roll)  (ROS/tf2 convention)
    r[0] = cy * cp;
    r[1] = cy * sp * sr - sy * cr;
    r[2] = cy * sp * cr + sy * sr;

    r[3] = sy * cp;
    r[4] = sy * sp * sr + cy * cr;
    r[5] = sy * sp * cr - cy * sr;

    r[6] = -sp;
    r[7] = cp * sr;
    r[8] = cp * cr;
  }

  static Rotation multiply(const Rotation & a, const Rotation & b)
  {
    // a * b (row-major 3x3)
    Rotation out;
    for (int i = 0; i < 3; ++i) {
      for (int j = 0; j < 3; ++j) {
        double s = 0.0;
        for (int k = 0; k < 3; ++k) {
          s += a.r[i * 3 + k] * b.r[k * 3 + j];
        }
        out.r[i * 3 + j] = s;
      }
    }
    return out;
  }
};

class CloudAlignNode : public rclcpp::Node
{
public:
  CloudAlignNode()
  : rclcpp::Node("l1_cloud_align_node")
  {
    input_topic_ = declare_parameter<std::string>("input_topic", "/unilidar/cloud");
    output_topic_ = declare_parameter<std::string>("output_topic", "/unilidar/cloud_aligned");
    target_frame_ = declare_parameter<std::string>("target_frame", "base_link");

    const auto xyz = declare_parameter<std::vector<double>>(
      "xyz", std::vector<double>{0.0, 0.0, 0.0});
    const auto base_rpy = declare_parameter<std::vector<double>>(
      "base_rpy_rad", std::vector<double>{0.0, 0.0, 0.0});
    const auto trim_rpy = declare_parameter<std::vector<double>>(
      "trim_rpy_rad", std::vector<double>{0.0, 0.0, 0.0});
    set_transform(xyz, base_rpy, trim_rpy);

    param_cb_ = add_on_set_parameters_callback(
      [this](const std::vector<rclcpp::Parameter> & params) {
        rcl_interfaces::msg::SetParametersResult result;
        result.successful = true;
        std::vector<double> new_xyz = tx_;
        std::vector<double> new_base = base_rpy_;
        std::vector<double> new_trim = trim_rpy_;
        for (const auto & p : params) {
          if (p.get_name() == "xyz") {
            new_xyz = p.as_double_array();
          } else if (p.get_name() == "base_rpy_rad") {
            new_base = p.as_double_array();
          } else if (p.get_name() == "trim_rpy_rad") {
            new_trim = p.as_double_array();
          } else if (p.get_name() == "target_frame") {
            target_frame_ = p.as_string();
          }
        }
        set_transform(new_xyz, new_base, new_trim);
        return result;
      });

    // Match unilidar_ros2 QoS: sensor_data (best-effort, small buffer).
    const auto qos = rclcpp::SensorDataQoS();
    pub_ = create_publisher<sensor_msgs::msg::PointCloud2>(output_topic_, qos);
    sub_ = create_subscription<sensor_msgs::msg::PointCloud2>(
      input_topic_, qos,
      std::bind(&CloudAlignNode::on_cloud, this, std::placeholders::_1));

    RCLCPP_INFO(
      get_logger(),
      "l1_cloud_align: %s -> %s (frame=%s) xyz=[%.3f,%.3f,%.3f] "
      "base_rpy=[%.3f,%.3f,%.3f] trim_rpy=[%.3f,%.3f,%.3f]",
      input_topic_.c_str(), output_topic_.c_str(), target_frame_.c_str(),
      tx_[0], tx_[1], tx_[2],
      base_rpy_[0], base_rpy_[1], base_rpy_[2],
      trim_rpy_[0], trim_rpy_[1], trim_rpy_[2]);
  }

private:
  void set_transform(
    const std::vector<double> & xyz,
    const std::vector<double> & base_rpy,
    const std::vector<double> & trim_rpy)
  {
    tx_ = (xyz.size() == 3) ? xyz : std::vector<double>{0.0, 0.0, 0.0};
    base_rpy_ = (base_rpy.size() == 3) ? base_rpy : std::vector<double>{0.0, 0.0, 0.0};
    trim_rpy_ = (trim_rpy.size() == 3) ? trim_rpy : std::vector<double>{0.0, 0.0, 0.0};
    Rotation r_base;
    Rotation r_trim;
    r_base.set_from_rpy(base_rpy_[0], base_rpy_[1], base_rpy_[2]);
    r_trim.set_from_rpy(trim_rpy_[0], trim_rpy_[1], trim_rpy_[2]);
    // R_final = R_trim_base * R_base_lidar
    // 先把 L1 原始坐标转到 base_link，再在 base_link 系里现场微调。
    rot_ = Rotation::multiply(r_trim, r_base);
  }

  static bool find_field(
    const sensor_msgs::msg::PointCloud2 & msg,
    const std::string & name,
    uint32_t & offset,
    uint8_t & datatype)
  {
    for (const auto & f : msg.fields) {
      if (f.name == name) {
        offset = f.offset;
        datatype = f.datatype;
        return true;
      }
    }
    return false;
  }

  void on_cloud(const sensor_msgs::msg::PointCloud2::SharedPtr in)
  {
    uint32_t off_x = 0;
    uint32_t off_y = 0;
    uint32_t off_z = 0;
    uint8_t dt_x = 0;
    uint8_t dt_y = 0;
    uint8_t dt_z = 0;
    if (!find_field(*in, "x", off_x, dt_x) ||
      !find_field(*in, "y", off_y, dt_y) ||
      !find_field(*in, "z", off_z, dt_z))
    {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "cloud missing x/y/z fields, dropping");
      return;
    }
    if (dt_x != sensor_msgs::msg::PointField::FLOAT32 ||
      dt_y != sensor_msgs::msg::PointField::FLOAT32 ||
      dt_z != sensor_msgs::msg::PointField::FLOAT32)
    {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "cloud x/y/z is not FLOAT32 (dt=%u/%u/%u), dropping",
        dt_x, dt_y, dt_z);
      return;
    }

    auto out = std::make_unique<sensor_msgs::msg::PointCloud2>(*in);
    out->header.frame_id = target_frame_;

    const size_t stride = out->point_step;
    const size_t count = static_cast<size_t>(out->width) * static_cast<size_t>(out->height);
    if (out->data.size() < count * stride) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 5000,
        "cloud data too small (%zu < %zu), dropping",
        out->data.size(), count * stride);
      return;
    }

    const double r00 = rot_.r[0];
    const double r01 = rot_.r[1];
    const double r02 = rot_.r[2];
    const double r10 = rot_.r[3];
    const double r11 = rot_.r[4];
    const double r12 = rot_.r[5];
    const double r20 = rot_.r[6];
    const double r21 = rot_.r[7];
    const double r22 = rot_.r[8];
    const double tx = tx_[0];
    const double ty = tx_[1];
    const double tz = tx_[2];

    uint8_t * base = out->data.data();
    for (size_t i = 0; i < count; ++i) {
      uint8_t * p = base + i * stride;
      float fx;
      float fy;
      float fz;
      std::memcpy(&fx, p + off_x, sizeof(float));
      std::memcpy(&fy, p + off_y, sizeof(float));
      std::memcpy(&fz, p + off_z, sizeof(float));
      if (!std::isfinite(fx) || !std::isfinite(fy) || !std::isfinite(fz)) {
        continue;
      }
      const double x = fx;
      const double y = fy;
      const double z = fz;
      const float nx = static_cast<float>(r00 * x + r01 * y + r02 * z + tx);
      const float ny = static_cast<float>(r10 * x + r11 * y + r12 * z + ty);
      const float nz = static_cast<float>(r20 * x + r21 * y + r22 * z + tz);
      std::memcpy(p + off_x, &nx, sizeof(float));
      std::memcpy(p + off_y, &ny, sizeof(float));
      std::memcpy(p + off_z, &nz, sizeof(float));
    }

    pub_->publish(std::move(out));
  }

  std::string input_topic_;
  std::string output_topic_;
  std::string target_frame_;
  std::vector<double> tx_{0.0, 0.0, 0.0};
  std::vector<double> base_rpy_{0.0, 0.0, 0.0};
  std::vector<double> trim_rpy_{0.0, 0.0, 0.0};
  Rotation rot_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr sub_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr pub_;
  rclcpp::Node::OnSetParametersCallbackHandle::SharedPtr param_cb_;
};

}  // namespace l1_cloud_align

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<l1_cloud_align::CloudAlignNode>());
  rclcpp::shutdown();
  return 0;
}
