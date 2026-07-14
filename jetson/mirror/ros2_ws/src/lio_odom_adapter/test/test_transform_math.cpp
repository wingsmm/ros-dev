#include <cmath>

#include "gtest/gtest.h"
#include "lio_odom_adapter/transform_math.hpp"

using lio_odom_adapter::Cov6;
using lio_odom_adapter::Quat;
using lio_odom_adapter::Rigid3;
using lio_odom_adapter::Twist6;
using lio_odom_adapter::Vec3;
using lio_odom_adapter::odom_base_from_imu;
using lio_odom_adapter::transform_covariance_imu_to_base;
using lio_odom_adapter::transform_twist_imu_to_base;

static constexpr double kEps = 1e-9;

TEST(TransformMath, IdentityPoseAndTwist)
{
  Rigid3 t_ci_imu{{1.0, 2.0, 3.0}, {0.0, 0.0, 0.0, 1.0}};
  Rigid3 t_base_imu{{0.0, 0.0, 0.0}, {0.0, 0.0, 0.0, 1.0}};
  Rigid3 t_odom_base = odom_base_from_imu(t_ci_imu, t_base_imu);
  EXPECT_NEAR(t_odom_base.translation.x, 1.0, kEps);
  EXPECT_NEAR(t_odom_base.translation.y, 2.0, kEps);
  EXPECT_NEAR(t_odom_base.translation.z, 3.0, kEps);
  EXPECT_NEAR(t_odom_base.rotation.w, 1.0, kEps);

  Twist6 tw{{0.5, -0.25, 0.1}, {0.0, 0.0, 0.2}};
  Twist6 out = transform_twist_imu_to_base(tw, t_base_imu);
  EXPECT_NEAR(out.linear.x, 0.5, kEps);
  EXPECT_NEAR(out.linear.y, -0.25, kEps);
  EXPECT_NEAR(out.linear.z, 0.1, kEps);
  EXPECT_NEAR(out.angular.z, 0.2, kEps);

  Cov6 cov{};
  cov[0] = 1.0;
  cov[7] = 2.0;
  Cov6 cov_out = transform_covariance_imu_to_base(cov, t_base_imu);
  EXPECT_NEAR(cov_out[0], 1.0, kEps);
  EXPECT_NEAR(cov_out[7], 2.0, kEps);
}

TEST(TransformMath, Yaw90Rotation)
{
  // Rz(90°): x->y, y->-x
  const double s = std::sqrt(0.5);
  Rigid3 t_base_imu{{0.0, 0.0, 0.0}, {0.0, 0.0, s, s}};
  Rigid3 t_ci_imu{{1.0, 0.0, 0.0}, {0.0, 0.0, 0.0, 1.0}};
  Rigid3 t_odom_base = odom_base_from_imu(t_ci_imu, t_base_imu);
  // inv(Rz90) = Rz(-90): translation of odom_base = Rz(-90)*[1,0,0] wait:
  // T_odom_base = T_ci_imu * inv(T_base_imu)
  // inv(T_base_imu) has R=Rz(-90), t=0
  // compose: R = I * Rz(-90), t = [1,0,0]
  EXPECT_NEAR(t_odom_base.translation.x, 1.0, kEps);
  EXPECT_NEAR(t_odom_base.translation.y, 0.0, kEps);
  EXPECT_NEAR(t_odom_base.rotation.z, -s, 1e-6);
  EXPECT_NEAR(t_odom_base.rotation.w, s, 1e-6);

  Twist6 tw{{1.0, 0.0, 0.0}, {0.0, 0.0, 1.0}};
  Twist6 out = transform_twist_imu_to_base(tw, t_base_imu);
  // R*[1,0,0] = [0,1,0]; ω' = R*[0,0,1]=[0,0,1]
  EXPECT_NEAR(out.linear.x, 0.0, 1e-6);
  EXPECT_NEAR(out.linear.y, 1.0, 1e-6);
  EXPECT_NEAR(out.angular.z, 1.0, 1e-6);
}

TEST(TransformMath, LeverArmTranslation)
{
  Rigid3 t_base_imu{{0.1, 0.0, 0.0}, {0.0, 0.0, 0.0, 1.0}};
  Rigid3 t_ci_imu{{0.0, 0.0, 0.0}, {0.0, 0.0, 0.0, 1.0}};
  Rigid3 t_odom_base = odom_base_from_imu(t_ci_imu, t_base_imu);
  // inv(t): translation = -0.1
  EXPECT_NEAR(t_odom_base.translation.x, -0.1, kEps);
  EXPECT_NEAR(t_odom_base.translation.y, 0.0, kEps);

  // v_base = v + t × ω; ω=z-hat => t×ω = [0.1,0,0]×[0,0,1] = [0,-0.1,0]?
  // i(0) - j(0.1*1) + k(0) = (0, -0.1, 0)
  Twist6 tw{{0.0, 0.0, 0.0}, {0.0, 0.0, 1.0}};
  Twist6 out = transform_twist_imu_to_base(tw, t_base_imu);
  EXPECT_NEAR(out.linear.x, 0.0, kEps);
  EXPECT_NEAR(out.linear.y, -0.1, kEps);
  EXPECT_NEAR(out.linear.z, 0.0, kEps);
  EXPECT_NEAR(out.angular.z, 1.0, kEps);
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
