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
if /I "%CMD%"=="record" goto :stack
if /I "%CMD%"=="status" goto :status
if /I "%CMD%"=="pull" goto :pull
echo [ERR] unknown command: %CMD%
goto :help

:help
echo Usage: deploy_laser_odom_compare.bat [deploy^|build^|start^|stop^|record^|status^|pull ^<bag_basename^>^|help]
echo.
echo   deploy   Sync stack script, analyze tool, laser_odometry, json_bridge; catkin_make
echo   build    catkin_make only
echo   start    Run laser_odom_compare_stack.sh start on robot (no upload)
echo   stop     Run laser_odom_compare_stack.sh stop on robot (no upload)
echo   record   Run laser_odom_compare_stack.sh record on robot (no upload)
echo   status   Topics, bags, stack logs (no upload)
echo   pull     Download bag and analysis reports to xtark/record/
echo   help     Show this help
echo.
echo Default with no arguments: deploy
exit /b 0

:deploy
echo [1/5] sync laser_odom_compare_stack.sh + analyze_laser_odom_bag.py ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "mkdir -p %XTARK_REMOTE_TOOLS%"
if errorlevel 1 exit /b 1
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%REPO_ROOT%xtark\scripts\laser_odom_compare_stack.sh" "%XTARK_REMOTE%:%XTARK_REMOTE_SCRIPTS%/laser_odom_compare_stack.sh"
if errorlevel 1 exit /b 1
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%REPO_ROOT%xtark\tools\analyze_laser_odom_bag.py" "%XTARK_REMOTE%:%XTARK_REMOTE_TOOLS%/analyze_laser_odom_bag.py"
if errorlevel 1 exit /b 1

echo [2/5] sync xtark_laser_odometry ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% -r "%REPO_ROOT%xtark\xtark_laser_odometry" %XTARK_REMOTE%:%XTARK_REMOTE_WS%/src/
if errorlevel 1 exit /b 1

echo [3/5] sync xtark_json_bridge ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% -r "%REPO_ROOT%xtark\xtark_json_bridge" %XTARK_REMOTE%:%XTARK_REMOTE_WS%/src/
if errorlevel 1 exit /b 1

:build_only
echo [4/5] chmod + catkin_make ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "chmod +x %XTARK_REMOTE_SCRIPTS%/laser_odom_compare_stack.sh %XTARK_REMOTE_TOOLS%/analyze_laser_odom_bag.py && cd %XTARK_REMOTE_WS% && source /opt/ros/melodic/setup.bash && catkin_make"
if errorlevel 1 exit /b 1

echo [5/5] verify packages ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && rospack find rf2o_laser_odometry && rospack find xtark_laser_odometry && rospack find xtark_json_bridge"
exit /b %ERRORLEVEL%

:stack
echo running laser_odom_compare_stack.sh %CMD% ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && %XTARK_REMOTE_SCRIPTS%/laser_odom_compare_stack.sh %CMD%"
exit /b %ERRORLEVEL%

:status
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && export ROS_MASTER_URI=http://%XTARK_HOST%:11311 && export ROS_IP=%XTARK_HOST% && %XTARK_REMOTE_SCRIPTS%/laser_odom_compare_stack.sh logs 2>/dev/null; echo ---topics---; rostopic list 2>/dev/null | grep -E 'cmd_vel|odom|scan|xtark' || true; echo ---bags---; ls -lt /home/xtark/xtark_logs/laser_odom_compare/bags 2>/dev/null | head -5"
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
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%XTARK_REMOTE%:/home/xtark/xtark_logs/laser_odom_compare/bags/%BAG_NAME%.bag" "%RECORD_BAG%\"
if errorlevel 1 exit /b 1
echo [2/3] pull analysis reports ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%XTARK_REMOTE%:/home/xtark/xtark_logs/laser_odom_compare/analysis_%STEM%.txt" "%RECORD_REPORT%\" 2>nul
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%XTARK_REMOTE%:/home/xtark/xtark_logs/laser_odom_compare/analysis_%STEM%.html" "%RECORD_REPORT%\" 2>nul
echo [3/3] local files:
dir /b "%RECORD_BAG%\%BAG_NAME%.bag" 2>nul
dir /b "%RECORD_REPORT%\analysis_%STEM%.*" 2>nul
exit /b 0
