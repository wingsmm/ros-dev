cmake_minimum_required(VERSION 3.0.2)
project(xtark_nav)

find_package(catkin REQUIRED)

catkin_package()

install(DIRECTORY launch config
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

catkin_install_python(PROGRAMS
  scripts/publish_robot_pose_in_map.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
