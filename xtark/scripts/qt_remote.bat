@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI\"
cd /d "%REPO_ROOT%"
call "%~dp0_xtark_remote_env.bat"

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

if /I "%CMD%"=="help" goto :help
if /I "%CMD%"=="-h" goto :help
if /I "%CMD%"=="--help" goto :help
if /I "%CMD%"=="deploy" goto :deploy
if /I "%CMD%"=="build" goto :build_only
if /I "%CMD%"=="start" goto :stack
if /I "%CMD%"=="stop" goto :stack
if /I "%CMD%"=="restart" goto :stack
if /I "%CMD%"=="status" goto :status
if /I "%CMD%"=="logs" goto :stack
if /I "%CMD%"=="record" goto :stack
if /I "%CMD%"=="pull" goto :pull
echo [ERR] unknown command: %CMD%
goto :help

:help
echo Usage: qt_remote.bat [deploy^|build^|start^|stop^|restart^|status^|logs^|record^|pull ^<bag_basename^>^|help]
echo.
echo   deploy   Sync qt_stack + packages, catkin_make
echo   build    catkin_make only
echo   start    qt_stack.sh start on robot (no upload)
echo   stop     qt_stack.sh stop
echo   restart  qt_stack.sh restart
echo   status   qt_stack.sh status + topics
echo   logs     qt_stack.sh logs
echo   record   qt_stack.sh record
echo   pull     Download qt_stack bag + analysis to xtark/record/
echo   help     Show this help
echo.
echo Default with no arguments: deploy
exit /b 0

:deploy
echo [1/6] sync qt_stack.sh stack_common.sh wrappers ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "mkdir -p %XTARK_REMOTE_TOOLS%"
if errorlevel 1 exit /b 1
for %%F in (qt_stack.sh stack_common.sh robot_stack.sh laser_odom_compare_stack.sh robot_control_stack.sh) do (
    "%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%REPO_ROOT%xtark\scripts\%%F" "%XTARK_REMOTE%:%XTARK_REMOTE_SCRIPTS%/%%F"
    if errorlevel 1 exit /b 1
)

echo [2/6] sync analyze_laser_odom_bag.py ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%REPO_ROOT%xtark\tools\analyze_laser_odom_bag.py" "%XTARK_REMOTE%:%XTARK_REMOTE_TOOLS%/analyze_laser_odom_bag.py"
if errorlevel 1 exit /b 1

echo [3/6] sync xtark_laser_odometry ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% -r "%REPO_ROOT%xtark\xtark_laser_odometry" %XTARK_REMOTE%:%XTARK_REMOTE_WS%/src/
if errorlevel 1 exit /b 1

echo [4/6] sync xtark_json_bridge ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% -r "%REPO_ROOT%xtark\xtark_json_bridge" %XTARK_REMOTE%:%XTARK_REMOTE_WS%/src/
if errorlevel 1 exit /b 1

:build_only
echo [5/6] chmod + strip CRLF + catkin_make ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "for f in %XTARK_REMOTE_SCRIPTS%/qt_stack.sh %XTARK_REMOTE_SCRIPTS%/stack_common.sh %XTARK_REMOTE_SCRIPTS%/robot_stack.sh %XTARK_REMOTE_SCRIPTS%/laser_odom_compare_stack.sh %XTARK_REMOTE_SCRIPTS%/robot_control_stack.sh %XTARK_REMOTE_TOOLS%/analyze_laser_odom_bag.py; do sed -i 's/\r$//' \"$f\"; chmod +x \"$f\"; done && cd %XTARK_REMOTE_WS% && source /opt/ros/melodic/setup.bash && catkin_make"
if errorlevel 1 exit /b 1

echo [6/6] verify packages ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && rospack find rf2o_laser_odometry && rospack find xtark_laser_odometry && rospack find xtark_json_bridge"
exit /b %ERRORLEVEL%

:stack
echo running qt_stack.sh %CMD% ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && export ROS_MASTER_URI=http://%XTARK_HOST%:11311 && export ROS_IP=%XTARK_HOST% && %XTARK_REMOTE_SCRIPTS%/qt_stack.sh %CMD%"
exit /b %ERRORLEVEL%

:status
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && export ROS_MASTER_URI=http://%XTARK_HOST%:11311 && export ROS_IP=%XTARK_HOST% && %XTARK_REMOTE_SCRIPTS%/qt_stack.sh status && echo ---bags--- && ls -lt /home/xtark/xtark_logs/qt_stack/bags 2>/dev/null | head -5"
exit /b %ERRORLEVEL%

:pull
set "BAG_NAME=%~2"
if "%BAG_NAME%"=="" (
    echo [ERR] pull requires bag basename, e.g. qt_stack_20260624_120000
    exit /b 1
)
set "RECORD_BAG=%REPO_ROOT%xtark\record\bags"
set "RECORD_REPORT=%REPO_ROOT%xtark\record\reports"
if not exist "%RECORD_BAG%" mkdir "%RECORD_BAG%"
if not exist "%RECORD_REPORT%" mkdir "%RECORD_REPORT%"
set "STEM=%BAG_NAME:qt_stack_=%"
echo [1/3] pull bag %BAG_NAME%.bag ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%XTARK_REMOTE%:/home/xtark/xtark_logs/qt_stack/bags/%BAG_NAME%.bag" "%RECORD_BAG%\"
if errorlevel 1 exit /b 1
echo [2/3] pull analysis reports ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%XTARK_REMOTE%:/home/xtark/xtark_logs/qt_stack/analysis_%STEM%.txt" "%RECORD_REPORT%\" 2>nul
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%XTARK_REMOTE%:/home/xtark/xtark_logs/qt_stack/analysis_%STEM%.html" "%RECORD_REPORT%\" 2>nul
echo [3/3] local files:
dir /b "%RECORD_BAG%\%BAG_NAME%.bag" 2>nul
dir /b "%RECORD_REPORT%\analysis_%STEM%.*" 2>nul
exit /b 0
