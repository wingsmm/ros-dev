cmake_minimum_required(VERSION 3.0.2)
project(xtark_json_bridge)

find_package(catkin REQUIRED COMPONENTS
  geometry_msgs
  nav_msgs
  rospy
  std_msgs
  tf
)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/json_base_adapter_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch config
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)
