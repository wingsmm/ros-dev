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
if /I "%CMD%"=="camera-start" goto :stack
if /I "%CMD%"=="camera-stop" goto :stack
if /I "%CMD%"=="camera-status" goto :stack
if /I "%CMD%"=="camera-check" goto :stack
if /I "%CMD%"=="camera-deep-start" goto :stack
if /I "%CMD%"=="camera-deep-stop" goto :stack
if /I "%CMD%"=="camera-deep-status" goto :stack
if /I "%CMD%"=="camera-deep-check" goto :stack
if /I "%CMD%"=="radar2d-start" goto :stack
if /I "%CMD%"=="radar2d-stop" goto :stack
if /I "%CMD%"=="radar2d-status" goto :stack
if /I "%CMD%"=="radar2d-check" goto :stack
if /I "%CMD%"=="full-start" goto :stack
if /I "%CMD%"=="full-stop" goto :stack
if /I "%CMD%"=="full-status" goto :stack
if /I "%CMD%"=="full-check" goto :stack
if /I "%CMD%"=="start" goto :stack
if /I "%CMD%"=="stop" goto :stack
if /I "%CMD%"=="restart" goto :stack
if /I "%CMD%"=="status" goto :stack
if /I "%CMD%"=="check" goto :stack
if /I "%CMD%"=="logs" goto :stack
echo [ERR] unknown command: %CMD%
goto :help

:help
echo Usage: pc_stack_remote.bat [deploy^|camera-start^|radar2d-start^|full-start^|...^|help]
echo.
echo   deploy        Sync pc_stack scripts to robot (%XTARK_HOST%)
echo   camera-start       pc_stack camera-start (RGB + depth raw, no preview)
echo   camera-deep-start  camera + depth_preview (/camera/depth/preview)
echo   camera-deep-stop / camera-deep-status / camera-deep-check
echo   radar2d-start pc_stack radar2d-start on robot
echo   full-start    pc_stack full-start (alias: start)
echo   *-stop / *-status / *-check / logs - same prefix on robot
echo   help          Show this help
echo.
echo VMware Qt on VM is a pure client; start pc_stack on robot manually or via this script.
echo Default with no arguments: deploy
exit /b 0

:deploy
echo [1/2] sync pc_stack scripts to robot ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "mkdir -p %XTARK_REMOTE_SCRIPTS%"
if errorlevel 1 exit /b 1
for %%F in (pc_stack.sh pc_stack_modules.sh stack_common.sh) do (
    "%PSCP%" -batch -hostkey "%XTARK_HOSTKEY%" -pw %XTARK_PASSWORD% "%REPO_ROOT%xtark\scripts\%%F" "%XTARK_REMOTE%:%XTARK_REMOTE_SCRIPTS%/%%F"
    if errorlevel 1 exit /b 1
)

echo [2/2] chmod + strip CRLF ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "for f in %XTARK_REMOTE_SCRIPTS%/pc_stack.sh %XTARK_REMOTE_SCRIPTS%/pc_stack_modules.sh %XTARK_REMOTE_SCRIPTS%/stack_common.sh; do sed -i 's/\r$//' \"$f\"; chmod +x \"$f\"; done"
exit /b %ERRORLEVEL%

:stack
echo running pc_stack.sh %CMD% on robot %XTARK_HOST% ...
"%PLINK%" -ssh %XTARK_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_HOSTKEY%" "source /opt/ros/melodic/setup.bash && source %XTARK_REMOTE_WS%/devel/setup.bash && export ROS_MASTER_URI=http://%XTARK_HOST%:11311 && export ROS_IP=%XTARK_HOST% && %XTARK_REMOTE_SCRIPTS%/pc_stack.sh %CMD%"
exit /b %ERRORLEVEL%
