#pragma once

#include <array>
#include <cmath>
#include <stdexcept>

namespace lio_odom_adapter
{

struct Vec3
{
  double x{0.0};
  double y{0.0};
  double z{0.0};
};

struct Quat
{
  double x{0.0};
  double y{0.0};
  double z{0.0};
  double w{1.0};
};

struct Twist6
{
  Vec3 linear;
  Vec3 angular;
};

using Cov6 = std::array<double, 36>;

inline bool finite_vec3(const Vec3 & v)
{
  return std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.z);
}

inline bool finite_quat(const Quat & q)
{
  return std::isfinite(q.x) && std::isfinite(q.y) && std::isfinite(q.z) &&
         std::isfinite(q.w);
}

inline Vec3 cross(const Vec3 & a, const Vec3 & b)
{
  return {
    a.y * b.z - a.z * b.y,
    a.z * b.x - a.x * b.z,
    a.x * b.y - a.y * b.x};
}

inline Vec3 rotate(const Quat & q, const Vec3 & v)
{
  const Vec3 qv{q.x, q.y, q.z};
  const Vec3 uv = cross(qv, v);
  const Vec3 uuv = cross(qv, uv);
  return {
    v.x + 2.0 * (q.w * uv.x + uuv.x),
    v.y + 2.0 * (q.w * uv.y + uuv.y),
    v.z + 2.0 * (q.w * uv.z + uuv.z)};
}

inline Quat quat_conj(const Quat & q)
{
  return {-q.x, -q.y, -q.z, q.w};
}

inline Quat quat_mul(const Quat & a, const Quat & b)
{
  return {
    a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z};
}

inline Quat quat_normalize(const Quat & q)
{
  const double n = std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
  if (!(n > 0.0) || !std::isfinite(n)) {
    throw std::runtime_error("non-finite quaternion");
  }
  return {q.x / n, q.y / n, q.z / n, q.w / n};
}

struct Rigid3
{
  Vec3 translation;
  Quat rotation;
};

inline Rigid3 inverse(const Rigid3 & t)
{
  const Quat r_inv = quat_conj(t.rotation);
  const Vec3 t_inv = rotate(r_inv, Vec3{-t.translation.x, -t.translation.y, -t.translation.z});
  return {t_inv, r_inv};
}

inline Rigid3 compose(const Rigid3 & a, const Rigid3 & b)
{
  // T = a * b : p' = Ra*(Rb*p + tb) + ta
  const Vec3 rb = rotate(a.rotation, b.translation);
  return {
    Vec3{
      a.translation.x + rb.x,
      a.translation.y + rb.y,
      a.translation.z + rb.z},
    quat_normalize(quat_mul(a.rotation, b.rotation))};
}

/**
 * Convert Point-LIO pose (T_camera_init_imu) to T_odom_base.
 * odom coincides with camera_init; T_odom_base = T_camera_init_imu * inv(T_base_imu).
 */
inline Rigid3 odom_base_from_imu(
  const Rigid3 & t_camera_init_imu,
  const Rigid3 & t_base_imu)
{
  return compose(t_camera_init_imu, inverse(t_base_imu));
}

/**
 * Twist adjoint: ξ_base = Ad_{T_base_imu} * ξ_imu
 * with ξ = [v; ω] (linear then angular), both expressed in body frames.
 *
 * Ad = | R     [t]^ R |
 *      | 0       R    |
 */
inline Twist6 transform_twist_imu_to_base(
  const Twist6 & twist_imu,
  const Rigid3 & t_base_imu)
{
  const Vec3 & t = t_base_imu.translation;
  const Quat & R = t_base_imu.rotation;
  const Vec3 v_rot = rotate(R, twist_imu.linear);
  const Vec3 w_rot = rotate(R, twist_imu.angular);
  const Vec3 lever = cross(t, w_rot);
  return {
    Vec3{v_rot.x + lever.x, v_rot.y + lever.y, v_rot.z + lever.z},
    w_rot};
}

inline void mat6_mul(const Cov6 & a, const Cov6 & b, Cov6 & out)
{
  for (int i = 0; i < 6; ++i) {
    for (int j = 0; j < 6; ++j) {
      double s = 0.0;
      for (int k = 0; k < 6; ++k) {
        s += a[static_cast<size_t>(i * 6 + k)] * b[static_cast<size_t>(k * 6 + j)];
      }
      out[static_cast<size_t>(i * 6 + j)] = s;
    }
  }
}

inline Cov6 mat6_transpose(const Cov6 & a)
{
  Cov6 out{};
  for (int i = 0; i < 6; ++i) {
    for (int j = 0; j < 6; ++j) {
      out[static_cast<size_t>(j * 6 + i)] = a[static_cast<size_t>(i * 6 + j)];
    }
  }
  return out;
}

inline Cov6 adjoint_matrix(const Rigid3 & t_base_imu)
{
  // Build rotation matrix from quaternion.
  const double x = t_base_imu.rotation.x;
  const double y = t_base_imu.rotation.y;
  const double z = t_base_imu.rotation.z;
  const double w = t_base_imu.rotation.w;
  const double R[3][3] = {
    {1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)},
    {2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)},
    {2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)},
  };
  const double tx = t_base_imu.translation.x;
  const double ty = t_base_imu.translation.y;
  const double tz = t_base_imu.translation.z;

  // [t]^ R
  double tXR[3][3];
  for (int j = 0; j < 3; ++j) {
    const double rx = R[0][j];
    const double ry = R[1][j];
    const double rz = R[2][j];
    tXR[0][j] = ty * rz - tz * ry;
    tXR[1][j] = tz * rx - tx * rz;
    tXR[2][j] = tx * ry - ty * rx;
  }

  Cov6 Ad{};
  for (int i = 0; i < 3; ++i) {
    for (int j = 0; j < 3; ++j) {
      Ad[static_cast<size_t>(i * 6 + j)] = R[i][j];
      Ad[static_cast<size_t>(i * 6 + (j + 3))] = tXR[i][j];
      Ad[static_cast<size_t>((i + 3) * 6 + j)] = 0.0;
      Ad[static_cast<size_t>((i + 3) * 6 + (j + 3))] = R[i][j];
    }
  }
  return Ad;
}

inline Cov6 transform_covariance_imu_to_base(
  const Cov6 & cov_imu,
  const Rigid3 & t_base_imu)
{
  const Cov6 Ad = adjoint_matrix(t_base_imu);
  Cov6 tmp{};
  Cov6 out{};
  mat6_mul(Ad, cov_imu, tmp);
  mat6_mul(tmp, mat6_transpose(Ad), out);
  return out;
}

}  // namespace lio_odom_adapter
