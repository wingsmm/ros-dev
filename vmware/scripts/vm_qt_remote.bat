@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI\"
cd /d "%REPO_ROOT%"
call "%REPO_ROOT%xtark\scripts\_xtark_remote_env.bat"
if not defined XTARK_VM_QT_ROOT set "XTARK_VM_QT_ROOT=/home/xtark/ros-dev/vmware/qt"

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
if not exist "%REPO_ROOT%vmware\qt\run.sh" (
    echo [ERR] vmware\qt not found under %REPO_ROOT%
    exit /b 1
)

if /I "%CMD%"=="help" goto :help
if /I "%CMD%"=="-h" goto :help
if /I "%CMD%"=="--help" goto :help
if /I "%CMD%"=="deploy" goto :deploy
if /I "%CMD%"=="astra-deploy" goto :astra_deploy
if /I "%CMD%"=="deps" goto :deps
if /I "%CMD%"=="status" goto :status
if /I "%CMD%"=="bootstrap" goto :bootstrap
if /I "%CMD%"=="run" goto :run
echo [ERR] unknown command: %CMD%
goto :help

:help
echo Usage: vm_qt_remote.bat [deploy^|astra-deploy^|deps^|status^|bootstrap^|run^|help]
echo.
echo   deploy        Sync vmware/qt to VM (%XTARK_VM_HOST%:%XTARK_VM_QT_ROOT%)
echo   astra-deploy  Sync astra_nearfield_ros1 + catkin_make --pkg (does NOT change Qt deploy)
echo   deps          Install python3-pyqt5 on VM (sudo)
echo   status        Remote file check + PyQt5 import test
echo   bootstrap     vmware/qt deploy + PyQt5 on VM (no pc_stack)
echo   run           Start GUI on VM desktop (needs local DISPLAY session)
echo   help          Show this help
echo.
echo One-time:  vm_qt_remote.bat bootstrap
echo Nearfield: vm_qt_remote.bat astra-deploy
echo Daily:     robot pc_stack camera-start, then VM ./run.sh
echo Default with no arguments: deploy
exit /b 0

:deploy
echo [1/3] mkdir %XTARK_VM_QT_ROOT% on VM ...
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "mkdir -p %XTARK_VM_QT_ROOT%"
if errorlevel 1 exit /b 1

echo [2/3] sync vmware/qt ...
"%PSCP%" -batch -hostkey "%XTARK_VM_HOSTKEY%" -pw %XTARK_PASSWORD% -r "%REPO_ROOT%vmware\qt" "%XTARK_VM_REMOTE%:/home/xtark/ros-dev/vmware/"
if errorlevel 1 exit /b 1

echo [3/3] chmod + strip CRLF + drop __pycache__ ...
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "find %XTARK_VM_QT_ROOT% -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null; find %XTARK_VM_QT_ROOT% -name '*.pyc' -delete 2>/dev/null; for f in %XTARK_VM_QT_ROOT%/run.sh; do sed -i 's/\r$//' \"$f\"; chmod +x \"$f\"; done"
exit /b %ERRORLEVEL%

:astra_deploy
if not defined XTARK_VM_ROS_WS set "XTARK_VM_ROS_WS=/home/xtark/ros_ws"
if not defined XTARK_VM_ASTRA_SRC set "XTARK_VM_ASTRA_SRC=%XTARK_VM_ROS_WS%/src/astra_nearfield_ros1"
echo [1/5] mkdir package path on VM (will not delete other src packages) ...
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "mkdir -p %XTARK_VM_ASTRA_SRC%"
if errorlevel 1 exit /b 1

echo [2/5] sync astra_nearfield_ros1 into %XTARK_VM_ROS_WS%/src/ (other packages untouched) ...
"%PSCP%" -batch -hostkey "%XTARK_VM_HOSTKEY%" -pw %XTARK_PASSWORD% -r "%REPO_ROOT%vmware\ros_ws\src\astra_nearfield_ros1" "%XTARK_VM_REMOTE%:%XTARK_VM_ROS_WS%/src/"
if errorlevel 1 exit /b 1

echo [3/5] strip CRLF + chmod scripts + ensure sparse pointcloud script ...
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "mkdir -p /home/xtark/ros-dev/vmware/qt/scripts; find %XTARK_VM_ASTRA_SRC% -type f \( -name '*.py' -o -name '*.sh' -o -name '*.launch' -o -name '*.yaml' -o -name 'CMakeLists.txt' -o -name 'package.xml' -o -name '*.md' \) -print0 | xargs -0 sed -i 's/\r$//'; chmod +x %XTARK_VM_ASTRA_SRC%/scripts/*.py %XTARK_VM_ASTRA_SRC%/scripts/*.sh 2>/dev/null; true"
if errorlevel 1 exit /b 1
"%PSCP%" -batch -hostkey "%XTARK_VM_HOSTKEY%" -pw %XTARK_PASSWORD% "%REPO_ROOT%vmware\qt\scripts\sparse_depth_pointcloud.py" "%XTARK_VM_REMOTE%:/home/xtark/ros-dev/vmware/qt/scripts/sparse_depth_pointcloud.py"
if errorlevel 1 exit /b 1
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "sed -i 's/\r$//' /home/xtark/ros-dev/vmware/qt/scripts/sparse_depth_pointcloud.py; chmod +x /home/xtark/ros-dev/vmware/qt/scripts/sparse_depth_pointcloud.py"
if errorlevel 1 exit /b 1

echo [4/5] catkin_make --pkg astra_nearfield_ros1 + devel lib symlinks ...
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "bash -lc 'source /opt/ros/melodic/setup.bash && cd %XTARK_VM_ROS_WS% && catkin_make --pkg astra_nearfield_ros1 && mkdir -p %XTARK_VM_ROS_WS%/devel/lib/astra_nearfield_ros1 && ln -sfn %XTARK_VM_ASTRA_SRC%/scripts/camera_tf_guard.py %XTARK_VM_ASTRA_SRC%/scripts/tf_edge_filter.py %XTARK_VM_ASTRA_SRC%/scripts/replay_probe.py %XTARK_VM_ASTRA_SRC%/scripts/astra_replay.sh %XTARK_VM_ROS_WS%/devel/lib/astra_nearfield_ros1/'"
if errorlevel 1 exit /b 1

echo [5/5] verify package discovery ...
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "bash -lc 'source /opt/ros/melodic/setup.bash && source %XTARK_VM_ROS_WS%/devel/setup.bash && rospack find astra_nearfield_ros1 && test -x %XTARK_VM_ROS_WS%/devel/lib/astra_nearfield_ros1/tf_edge_filter.py && test -x %XTARK_VM_ROS_WS%/devel/lib/astra_nearfield_ros1/replay_probe.py && test -x %XTARK_VM_ROS_WS%/devel/lib/astra_nearfield_ros1/astra_replay.sh && test -x %XTARK_VM_ROS_WS%/devel/lib/astra_nearfield_ros1/camera_tf_guard.py && test -f %XTARK_VM_ASTRA_SRC%/launch/camera_tf.launch && python2 %XTARK_VM_ASTRA_SRC%/test/test_tf_edge_filter.py && echo ASTRA_DEPLOY_OK'"
exit /b %ERRORLEVEL%

:deps
echo installing python3-pyqt5 on %XTARK_VM_HOST% ...
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "echo %XTARK_PASSWORD% | sudo -S DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pyqt5"
exit /b %ERRORLEVEL%

:status
echo === vmware qt client on %XTARK_VM_HOST% ===
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "echo QT_ROOT=%XTARK_VM_QT_ROOT%; ls -la %XTARK_VM_QT_ROOT%/run.sh %XTARK_VM_QT_ROOT%/app.py 2>&1; python3 -c \"import PyQt5.QtWidgets; print('PyQt5: OK')\" 2>&1"
exit /b %ERRORLEVEL%

:bootstrap
echo [bootstrap 1/2] vmware/qt to VM ...
call "%~dp0vm_qt_remote.bat" deploy
if errorlevel 1 exit /b 1
echo [bootstrap 2/2] PyQt5 on VM ...
call "%~dp0vm_qt_remote.bat" deps
exit /b %ERRORLEVEL%

:run
echo starting VMware Qt client on VM desktop (DISPLAY=:0) ...
"%PLINK%" -ssh %XTARK_VM_REMOTE% -pw %XTARK_PASSWORD% -batch -hostkey "%XTARK_VM_HOSTKEY%" "export DISPLAY=:0; cd %XTARK_VM_QT_ROOT% && ./run.sh"
exit /b %ERRORLEVEL%
