@echo off
setlocal EnableExtensions

set "PLINK=C:\Program Files\PuTTY\plink.exe"
set "HOSTKEY=SHA256:hrGvBYXQfk9JH6fq71t0BYZEoulJ5WjZomhk5NlkLOY"

"%PLINK%" -ssh xtark@192.168.1.169 -pw xtark -batch -hostkey "%HOSTKEY%" "source /opt/ros/melodic/setup.bash; source /home/xtark/ros_ws/devel/setup.bash; export ROS_MASTER_URI=http://192.168.1.169:11311; export ROS_IP=192.168.1.169; /home/xtark/ros_ws/scripts/android_stack.sh status; echo ---nodes---; rosnode list; echo ---logs---; tail -80 /home/xtark/xtark_logs/android/bringup.log 2>/dev/null"
exit /b %ERRORLEVEL%
