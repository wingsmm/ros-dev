cmake_minimum_required(VERSION 3.0.2)
project(astra_nearfield_ros1)

find_package(catkin REQUIRED COMPONENTS
  geometry_msgs
  rospy
  tf
  tf2_msgs
  tf2_ros
)

catkin_package()

catkin_install_python(
  PROGRAMS scripts/camera_tf_guard.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(
  DIRECTORY config launch
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)
