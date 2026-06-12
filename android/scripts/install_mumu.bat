@echo off
REM ============================================================================
REM install_mumu.bat - install xtark Control ALT APK to MuMu emulator
REM
REM Usage (from android/):
REM   scripts\install_mumu.bat
REM
REM Prerequisites:
REM   1. scripts\build_app.bat has produced apks\xtark-control-alt-debug.apk
REM   2. MuMu emulator is running and ready
REM
REM Note: mumu-cli may return exit code 0 while JSON contains errcode; always
REM       validate command output, not only ERRORLEVEL.
REM ============================================================================
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..") do set "ROOT=%%~fI\"
cd /d "%ROOT%"

REM --- config ---
set "APK=%ROOT%apks\xtark-control-alt-debug.apk"
set "MUMU_CLI=D:\Program Files\Netease\MuMu\nx_main\mumu-cli.exe"
set "PKG=cn.xtark.robotca"
set "VMINDEX=0"
set "STEP_TOTAL=5"
set "MUMU_OUT=%TEMP%\mumu_deploy_%RANDOM%.txt"

echo ============================================================
echo Deploy xtark Control ALT to MuMu
echo package: %PKG%
echo apk: %APK%
echo ============================================================

goto :run

REM ============================================================================
REM subroutines (main flow must not fall through here)
REM ============================================================================

:step_banner
REM arg1 = step title
echo.
echo ------------------------------------------------------------
echo [STEP %STEP_N%/%STEP_TOTAL%] %~1
echo ------------------------------------------------------------
exit /b 0

:require_file
REM arg1 = path, arg2 = error message
if not exist "%~1" (
  echo [ERR] %~2
  echo       path: %~1
  exit /b 1
)
exit /b 0

:require_file_size
REM arg1 = path, arg2 = error message
for %%F in ("%~1") do set "_SIZE=%%~zF"
if not defined _SIZE set "_SIZE=0"
if !_SIZE! LEQ 0 (
  echo [ERR] %~2
  echo       path: %~1
  exit /b 1
)
exit /b 0

:mumu_run
REM run mumu-cli adb; capture output to MUMU_OUT; arg1 = adb subcommand
set "MUMU_CMD=%~1"
del "%MUMU_OUT%" >nul 2>&1
"%MUMU_CLI%" adb --vmindex %VMINDEX% --cmd "%MUMU_CMD%" > "%MUMU_OUT%" 2>&1
exit /b !ERRORLEVEL!

:assert_no_mumu_errcode
REM fail if JSON output contains errcode (connect errors hide behind exit 0)
findstr /c:"\"errcode\"" "%MUMU_OUT%" >nul
if not errorlevel 1 (
  echo [ERR] %~1
  exit /b 1
)
exit /b 0

:assert_output_contains
REM arg1 = pattern, arg2 = error message
findstr /i /c:"%~1" "%MUMU_OUT%" >nul
if errorlevel 1 (
  echo [ERR] %~2
  exit /b 1
)
exit /b 0

:output_has
REM check pattern without failing; used for optional uninstall
findstr /i /c:"%~1" "%MUMU_OUT%" >nul
exit /b !ERRORLEVEL!

:show_output
if exist "%MUMU_OUT%" type "%MUMU_OUT%"
exit /b 0

:cleanup
del "%MUMU_OUT%" >nul 2>&1
exit /b 0

REM ============================================================================
REM main
REM ============================================================================

:run

REM step 1: check apk and mumu-cli
set "STEP_N=1"
call :step_banner "precheck"
call :require_file "%APK%" "apk missing, run build_app.bat alt first"
if errorlevel 1 goto :fail
call :require_file_size "%APK%" "apk file is empty"
if errorlevel 1 goto :fail
call :require_file "%MUMU_CLI%" "mumu-cli not found"
if errorlevel 1 goto :fail
for %%F in ("%APK%") do echo [OK] apk size=%%~zF bytes
echo [OK] mumu-cli=%MUMU_CLI%

REM step 2: adb connect
set "STEP_N=2"
call :step_banner "adb connect"
call :mumu_run "connect"
if errorlevel 1 goto :fail
call :assert_no_mumu_errcode "adb connect failed, MuMu VM not ready"
if errorlevel 1 goto :fail
call :assert_output_contains "connected to" "adb connect did not report connected device"
if errorlevel 1 goto :fail
echo [OK]
call :show_output

REM step 3: verify device online
set "STEP_N=3"
call :step_banner "adb devices"
call :mumu_run "devices"
if errorlevel 1 goto :fail
call :assert_output_contains "	device" "no online adb device found"
if errorlevel 1 goto :fail
echo [OK]
call :show_output

REM step 4: uninstall old package if present
set "STEP_N=4"
call :step_banner "uninstall old package"
call :mumu_run "uninstall %PKG%"
call :output_has "Success"
if not errorlevel 1 (
  echo [OK] old package removed
) else (
  echo [OK] package not installed, skip uninstall
  call :show_output
)

REM step 5: install apk and verify package name
set "STEP_N=5"
call :step_banner "install and verify"
call :mumu_run "install \"%APK%\""
if errorlevel 1 goto :fail
call :assert_output_contains "Success" "install did not report Success"
if errorlevel 1 goto :fail
echo [OK] install output:
call :show_output

call :mumu_run "shell pm list packages %PKG%"
if errorlevel 1 goto :fail
call :assert_output_contains "package:%PKG%" "package not found after install"
if errorlevel 1 goto :fail
echo [OK] verified package:%PKG%

call :cleanup
echo.
echo ============================================================
echo [OK] xtark Control ALT installed on MuMu
echo [OK] package=%PKG%
echo [OK] apk=%APK%
echo ============================================================
exit /b 0

:fail
echo.
echo --- last mumu-cli output ---
call :show_output
call :cleanup
exit /b 1
