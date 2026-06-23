@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI\"
cd /d "%REPO_ROOT%"
call "%~dp0_xtark_remote_env.bat"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=all"

if /I "%CMD%"=="help" goto :help
if /I "%CMD%"=="-h" goto :help
if /I "%CMD%"=="--help" goto :help
if /I "%CMD%"=="deploy" goto :deploy
if /I "%CMD%"=="start" goto :start
if /I "%CMD%"=="stop" goto :stop
if /I "%CMD%"=="status" goto :status
if /I "%CMD%"=="logs" goto :logs
if /I "%CMD%"=="watch-nav" goto :watch_nav
if /I "%CMD%"=="all" goto :all
echo [ERR] unknown command: %CMD%
goto :help

:help
echo Usage: android_remote.bat [deploy^|start^|stop^|status^|logs^|watch-nav^|all^|help]
echo.
echo   deploy     Upload android_stack.sh and xtark_nav only
echo   start      Run android_stack.sh start (no upload)
echo   stop       Run android_stack.sh stop (no upload)
echo   status     Stack status, rosnode list, recent logs (no upload)
echo   logs       Tail android_stack.sh logs (no upload)
echo   watch-nav  Live navigation debug (no upload)
echo   all        deploy then start
echo   help       Show this help
echo.
echo Default with no arguments: all
exit /b 0

:deploy
set "SCRIPT_SRC=%REPO_ROOT%xtark\scripts\android_stack.sh"
if not exist "%SCRIPT_SRC%" (
    echo [ERR] script missing: %SCRIPT_SRC%
    exit /b 1
)
if not exist "%PSCP%" (
    echo [ERR] pscp not found: %PSCP%
    exit /b 1
)
echo [1/3] sync android_stack.sh + xtark_nav ...
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%SCRIPT_SRC%" "%XTARK_REMOTE%:%XTARK_REMOTE_SCRIPTS%/android_stack.sh"
if errorlevel 1 exit /b 1
"%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% -r "%REPO_ROOT%xtark\xtark_nav" %XTARK_REMOTE%:%XTARK_REMOTE_WS%/src/
if errorlevel 1 exit /b 1
echo [2/3] chmod +x ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "chmod +x %XTARK_REMOTE_SCRIPTS%/android_stack.sh %XTARK_REMOTE_WS%/src/xtark_nav/scripts/publish_robot_pose_in_map.py"
if errorlevel 1 exit /b 1
echo [3/3] deploy done
exit /b 0

:start
call :run_android start
exit /b %ERRORLEVEL%

:stop
call :run_android stop
exit /b %ERRORLEVEL%

:logs
call :run_android logs
exit /b %ERRORLEVEL%

:watch_nav
call :run_android watch-nav
exit /b %ERRORLEVEL%

:status
if not exist "%PLINK%" (
    echo [ERR] plink not found: %PLINK%
    exit /b 1
)
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && export ROS_MASTER_URI=http://%XTARK_HOST%:11311 && export ROS_IP=%XTARK_HOST% && %XTARK_REMOTE_SCRIPTS%/android_stack.sh status && echo ---nodes--- && rosnode list && echo ---logs--- && tail -80 /home/xtark/xtark_logs/android/bringup.log 2>/dev/null"
exit /b %ERRORLEVEL%

:all
call "%~f0" deploy
if errorlevel 1 exit /b 1
call "%~f0" start
exit /b %ERRORLEVEL%

:run_android
set "STACK_CMD=%~1"
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && export ROS_MASTER_URI=http://%XTARK_HOST%:11311 && export ROS_IP=%XTARK_HOST% && %XTARK_REMOTE_SCRIPTS%/android_stack.sh %STACK_CMD%"
exit /b %ERRORLEVEL%
