@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "ROOT=%%~fI\"
cd /d "%ROOT%"

set "PLINK=C:\Program Files\PuTTY\plink.exe"
set "PSCP=C:\Program Files\PuTTY\pscp.exe"
set "HOSTKEY=SHA256:hrGvBYXQfk9JH6fq71t0BYZEoulJ5WjZomhk5NlkLOY"
set "SCRIPT_SRC=%ROOT%..\xtark\scripts\run_android.sh"
set "REMOTE=xtark@192.168.1.169:/home/xtark/ros_ws/scripts/run_android.sh"
set "CMD=%~1"
if "%CMD%"=="" set "CMD=start"

if not exist "%SCRIPT_SRC%" (
    echo [ERR] script missing: %SCRIPT_SRC%
    exit /b 1
)
if not exist "%PSCP%" (
    echo [ERR] pscp not found: %PSCP%
    exit /b 1
)

echo [1/3] sync run_android.sh + xtark_nav + pose script to 169 ...
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark "%SCRIPT_SRC%" "%REMOTE%"
if errorlevel 1 exit /b 1
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark "%ROOT%..\xtark\scripts\publish_robot_pose_in_map.py" xtark@192.168.1.169:/home/xtark/ros_ws/scripts/publish_robot_pose_in_map.py
if errorlevel 1 exit /b 1
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark -r "%ROOT%..\xtark\xtark_nav\config" xtark@192.168.1.169:/home/xtark/ros_ws/src/xtark_nav/
if errorlevel 1 exit /b 1
"%PSCP%" -batch -hostkey "%HOSTKEY%" -pw xtark -r "%ROOT%..\xtark\xtark_nav\launch" xtark@192.168.1.169:/home/xtark/ros_ws/src/xtark_nav/
if errorlevel 1 exit /b 1

echo [2/3] chmod +x ...
"%PLINK%" -ssh xtark@192.168.1.169 -pw xtark -batch -hostkey "%HOSTKEY%" "chmod +x /home/xtark/ros_ws/scripts/run_android.sh /home/xtark/ros_ws/scripts/publish_robot_pose_in_map.py"
if errorlevel 1 exit /b 1

echo [3/3] run_android.sh %CMD% ...
"%PLINK%" -ssh xtark@192.168.1.169 -pw xtark -batch -hostkey "%HOSTKEY%" "chmod +x /home/xtark/ros_ws/scripts/run_android.sh && /home/xtark/ros_ws/scripts/run_android.sh %CMD%"
exit /b %ERRORLEVEL%
