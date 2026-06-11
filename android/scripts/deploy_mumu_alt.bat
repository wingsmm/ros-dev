@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "ROOT=%%~fI\"
cd /d "%ROOT%"

set "APK=%ROOT%xtark-control-alt-debug.apk"
set "MUMU_CLI=D:\Program Files\Netease\MuMu\nx_main\mumu-cli.exe"
set "PKG=cn.xtark.robotca"

if not exist "%APK%" (
    echo [ERR] apk missing: %APK%
    echo run scripts\build_robotca_super.bat alt first
    exit /b 1
)
if not exist "%MUMU_CLI%" (
    echo [ERR] mumu-cli not found: %MUMU_CLI%
    exit /b 1
)

echo [1/3] adb connect ...
"%MUMU_CLI%" adb --vmindex 0 --cmd "connect"
if errorlevel 1 exit /b 1

echo [2/3] uninstall old %PKG% if any ...
"%MUMU_CLI%" adb --vmindex 0 --cmd "uninstall %PKG%"

echo [3/3] install %APK% ...
"%MUMU_CLI%" adb --vmindex 0 --cmd "install \"%APK%\""
if errorlevel 1 (
    echo [ERR] install failed
    exit /b 1
)

echo [OK] xtark Control ALT installed on MuMu  package=%PKG%
exit /b 0
