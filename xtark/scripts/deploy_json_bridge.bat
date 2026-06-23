@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI\"
cd /d "%REPO_ROOT%"
call "%~dp0_xtark_remote_env.bat"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=all"

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
if /I "%CMD%"=="restart" goto :restart
if /I "%CMD%"=="status" goto :status
if /I "%CMD%"=="all" goto :all
echo [ERR] unknown command: %CMD%
goto :help

:help
echo Usage: deploy_json_bridge.bat [deploy^|build^|restart^|status^|all^|help]
echo.
echo   deploy   Sync json_stack.sh, robot_control_stack.sh and xtark_json_bridge, then catkin_make
echo   build    catkin_make only (after files already on robot)
echo   restart  Restart json_base_adapter (no upload)
echo   status   Show adapter process, port 8765, recent log (no upload)
echo   all      deploy then restart
echo   help     Show this help
echo.
echo Default with no arguments: all
exit /b 0

:deploy
echo [1/4] sync json_stack.sh ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%REPO_ROOT%xtark\scripts\json_stack.sh" "%XTARK_REMOTE%:%XTARK_REMOTE_SCRIPTS%/json_stack.sh"
if errorlevel 1 exit /b 1

echo [2/4] sync robot_control_stack.sh ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%REPO_ROOT%xtark\scripts\robot_control_stack.sh" "%XTARK_REMOTE%:%XTARK_REMOTE_SCRIPTS%/robot_control_stack.sh"
if errorlevel 1 exit /b 1

echo [3/4] sync xtark_json_bridge ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% -r "%REPO_ROOT%xtark\xtark_json_bridge" %XTARK_REMOTE%:%XTARK_REMOTE_WS%/src/
if errorlevel 1 exit /b 1
goto :build_only

:build_only
echo [4/4] chmod + catkin_make ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "chmod +x %XTARK_REMOTE_SCRIPTS%/json_stack.sh %XTARK_REMOTE_SCRIPTS%/robot_control_stack.sh && cd %XTARK_REMOTE_WS% && source /opt/ros/melodic/setup.bash && catkin_make && source devel/setup.bash && rospack find xtark_json_bridge"
exit /b %ERRORLEVEL%

:restart
echo restarting json_base_adapter ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "pkill -f json_base_adapter.launch 2>/dev/null || true; pkill -f json_base_adapter_node.py 2>/dev/null || true; sleep 1; exit 0"
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && export ROS_MASTER_URI=http://%XTARK_HOST%:11311 && export ROS_IP=%XTARK_HOST% && mkdir -p /home/xtark/xtark_logs && nohup roslaunch xtark_json_bridge json_base_adapter.launch > /home/xtark/xtark_logs/json_adapter.log 2>&1 &"
if errorlevel 1 exit /b 1
timeout /t 3 /nobreak >nul
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "pgrep -af json_base_adapter_node.py || (echo [ERR] json adapter not running & exit 1)"
exit /b %ERRORLEVEL%

:status
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && export ROS_MASTER_URI=http://%XTARK_HOST%:11311 && export ROS_IP=%XTARK_HOST% && pgrep -af json_base_adapter_node.py || echo NO_JSON && ss -lnt | grep 8765 || echo PORT8765_DOWN && tail -15 /home/xtark/xtark_logs/json_adapter.log 2>/dev/null || true"
exit /b %ERRORLEVEL%

:all
call "%~f0" deploy
if errorlevel 1 exit /b 1
call "%~f0" restart
exit /b %ERRORLEVEL%
