@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI\"
cd /d "%REPO_ROOT%"

set "PLINK=C:\Program Files\PuTTY\plink.exe"
set "PSCP=C:\Program Files\PuTTY\pscp.exe"
set "HOSTKEY=SHA256:hrGvBYXQfk9JH6fq71t0BYZEoulJ5WjZomhk5NlkLOY"
set "REMOTE_SCRIPTS=xtark@192.168.1.169:/home/xtark/ros_ws/scripts"
set "CMD=%~1"
if "%CMD%"=="" set "CMD=deploy"

if not exist "%PSCP%" (
    echo [ERR] pscp not found: %PSCP%
    exit /b 1
)
if not exist "%PLINK%" (
    echo [ERR] plink not found: %PLINK%
    exit /b 1
)

if /I "%CMD%"=="deploy" goto :deploy
if /I "%CMD%"=="build" goto :build_only
if /I "%CMD%"=="start" goto :stack
if /I "%CMD%"=="stop" goto :stack
if /I "%CMD%"=="record" goto :stack
if /I "%CMD%"=="status" goto :status
if /I "%CMD%"=="pull" goto :pull
echo [ERR] unknown command: %CMD%
echo Usage: deploy_laser_odom_compare.bat [deploy^|build^|start^|stop^|record^|status^|pull ^<bag_basename^>]
exit /b 1

:deploy
echo [1/4] sync laser_odom_compare_stack.sh + analyze_laser_odom_bag.py ...
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark "%REPO_ROOT%xtark\scripts\laser_odom_compare_stack.sh" "%REMOTE_SCRIPTS%/laser_odom_compare_stack.sh"
if errorlevel 1 exit /b 1
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark "%REPO_ROOT%xtark\scripts\analyze_laser_odom_bag.py" "%REMOTE_SCRIPTS%/analyze_laser_odom_bag.py"
if errorlevel 1 exit /b 1

echo [2/4] sync xtark_laser_odometry ...
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark -r "%REPO_ROOT%xtark\xtark_laser_odometry" xtark@192.168.1.169:/home/xtark/ros_ws/src/
if errorlevel 1 exit /b 1

:build_only
echo [3/4] chmod + catkin_make ...
"%PLINK%" -ssh xtark@192.168.1.169 -pw xtark -batch -hostkey "%HOSTKEY%" "chmod +x /home/xtark/ros_ws/scripts/laser_odom_compare_stack.sh /home/xtark/ros_ws/scripts/analyze_laser_odom_bag.py && cd /home/xtark/ros_ws && source /opt/ros/melodic/setup.bash && catkin_make"
if errorlevel 1 exit /b 1

echo [4/4] verify packages ...
"%PLINK%" -ssh xtark@192.168.1.169 -pw xtark -batch -hostkey "%HOSTKEY%" "source /opt/ros/melodic/setup.bash && source /home/xtark/ros_ws/devel/setup.bash && rospack find rf2o_laser_odometry && rospack find xtark_laser_odometry"
exit /b %ERRORLEVEL%

:stack
echo running laser_odom_compare_stack.sh %CMD% ...
"%PLINK%" -ssh xtark@192.168.1.169 -pw xtark -batch -hostkey "%HOSTKEY%" "source /opt/ros/melodic/setup.bash && source /home/xtark/ros_ws/devel/setup.bash && /home/xtark/ros_ws/scripts/laser_odom_compare_stack.sh %CMD%"
exit /b %ERRORLEVEL%

:status
"%PLINK%" -ssh xtark@192.168.1.169 -pw xtark -batch -hostkey "%HOSTKEY%" "source /opt/ros/melodic/setup.bash && source /home/xtark/ros_ws/devel/setup.bash && export ROS_MASTER_URI=http://192.168.1.169:11311 && export ROS_IP=192.168.1.169 && /home/xtark/ros_ws/scripts/laser_odom_compare_stack.sh logs 2>/dev/null; echo ---topics---; rostopic list 2>/dev/null | grep -E 'cmd_vel|odom|scan|xtark' || true; echo ---bags---; ls -lt /home/xtark/xtark_logs/laser_odom_compare/bags 2>/dev/null | head -5"
exit /b %ERRORLEVEL%

:pull
set "BAG_NAME=%~2"
if "%BAG_NAME%"=="" (
    echo [ERR] pull requires bag basename, e.g. laser_odom_compare_20260623_095953
    exit /b 1
)
set "RECORD_BAG=%REPO_ROOT%xtark\record\bags"
set "RECORD_REPORT=%REPO_ROOT%xtark\record\reports"
if not exist "%RECORD_BAG%" mkdir "%RECORD_BAG%"
if not exist "%RECORD_REPORT%" mkdir "%RECORD_REPORT%"
set "STEM=%BAG_NAME:laser_odom_compare_=%"
echo [1/3] pull bag %BAG_NAME%.bag ...
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark "xtark@192.168.1.169:/home/xtark/xtark_logs/laser_odom_compare/bags/%BAG_NAME%.bag" "%RECORD_BAG%\"
if errorlevel 1 exit /b 1
echo [2/3] pull analysis reports ...
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark "xtark@192.168.1.169:/home/xtark/xtark_logs/laser_odom_compare/analysis_%STEM%.txt" "%RECORD_REPORT%\" 2>nul
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark "xtark@192.168.1.169:/home/xtark/xtark_logs/laser_odom_compare/analysis_%STEM%.html" "%RECORD_REPORT%\" 2>nul
echo [3/3] local files:
dir /b "%RECORD_BAG%\%BAG_NAME%.bag" 2>nul
dir /b "%RECORD_REPORT%\analysis_%STEM%.*" 2>nul
exit /b 0
