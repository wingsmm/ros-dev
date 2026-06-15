@echo off
REM ============================================================================
REM build_app.bat - build RobotCA APK for xtark Android app
REM
REM Usage (from android/):
REM   scripts\build_app.bat          default alt package cn.xtark.robotca
REM   scripts\build_app.bat orig     original package com.robotca.ControlApp
REM
REM Output:
REM   apks\xtark-control-alt-debug.apk       alt mode (default)
REM   apks\xtark-control-debug.apk             orig mode
REM ============================================================================
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..") do set "ROOT=%%~fI\"
cd /d "%ROOT%"

REM --- config ---
set "MODE=%~1"
if "%MODE%"=="" set "MODE=alt"
set "JDK=%ROOT%tools\jdk8"
set "SDK=D:\ProgramData\Android\sdk"
set "ROSJAVA=%ROOT%tools\rosjava_mvn_repo"
set "APP=%ROOT%RobotCA-master\RobotCA-master\src\android_foo\control_app"
set "APK=%APP%\build\outputs\apk\control_app-debug.apk"
set "APK_OUT_DIR=%ROOT%apks"
set "OUT=%APK_OUT_DIR%\xtark-control-alt-debug.apk"
set "APP_ID=cn.xtark.robotca"
set "VERSION_NAME=1.0-xtark-alt"
set "GRADLE_ARGS=--no-daemon assembleDebug -PappId=cn.xtark.robotca -PappVersionName=1.0-xtark-alt"
set "AAPT=%SDK%\build-tools\30.0.2\aapt.exe"
set "STEP_TOTAL=8"
set "BADGE=%TEMP%\robotca_badging_%RANDOM%.txt"

if /i "%MODE%"=="orig" (
  set "OUT=%APK_OUT_DIR%\xtark-control-debug.apk"
  set "APP_ID=com.robotca.ControlApp"
  set "VERSION_NAME=1.0-xtark"
  set "GRADLE_ARGS=--no-daemon assembleDebug"
)

echo ============================================================
echo RobotCA super build
echo mode: %MODE%
echo package: %APP_ID%
echo output: %OUT%
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

:require_path
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

:setup_java
REM verify JDK exists and runs; set JAVA_HOME and PATH
call :require_path "%JDK%\bin\java.exe" "JDK8 missing"
if errorlevel 1 exit /b 1
"%JDK%\bin\java.exe" -version
if errorlevel 1 (
  echo [ERR] JDK8 cannot run
  exit /b 1
)
set "JAVA_HOME=%JDK%"
set "PATH=%JDK%\bin;%SDK%\platform-tools;%PATH%"
echo [OK]
exit /b 0

:check_rosjava_repo
REM verify local rosjava Maven repo and required artifacts
call :require_path "%ROSJAVA%\.git" "rosjava repo missing, populate android\tools\rosjava_mvn_repo first"
if errorlevel 1 exit /b 1
call :require_path "%ROSJAVA%\org\ros\android_core\android_10\0.2.1" "missing android_10 0.2.1 in rosjava repo"
if errorlevel 1 exit /b 1
call :require_path "%ROSJAVA%\org\ros\android_core\android_15\0.2.1" "missing android_15 0.2.1 in rosjava repo"
if errorlevel 1 exit /b 1
call :require_path "%ROSJAVA%\com\github\rosjava\android_extras\gingerbread\0.2.0" "missing gingerbread 0.2.0 in rosjava repo"
if errorlevel 1 exit /b 1
call :require_path "%ROSJAVA%\org\ros\rosjava_messages\tf2_msgs\0.5.13" "missing tf2_msgs 0.5.13 in rosjava repo"
if errorlevel 1 exit /b 1
echo [OK]
exit /b 0

:check_appid_support
REM build.gradle must accept -PappId for alt package builds
call :require_path "%APP%\gradlew.bat" "gradlew.bat missing"
if errorlevel 1 exit /b 1
findstr /c:"applicationId project.hasProperty('appId')" "%APP%\build.gradle" >nul
if errorlevel 1 (
  echo [ERR] build.gradle does not support -PappId
  exit /b 1
)
echo [OK]
exit /b 0

:write_local_properties
>"%APP%\local.properties" echo sdk.dir=D\:\\ProgramData\\Android\\sdk
if errorlevel 1 (
  echo [ERR] failed to write local.properties
  exit /b 1
)
if not exist "%APP%\local.properties" (
  echo [ERR] local.properties missing after write
  exit /b 1
)
echo [OK]
exit /b 0

:run_gradle
cd /d "%APP%"
call "%APP%\gradlew.bat" %GRADLE_ARGS%
if errorlevel 1 (
  echo [ERR] Gradle build failed
  exit /b 1
)
echo [OK]
exit /b 0

:collect_apk
if not exist "%APK_OUT_DIR%" mkdir "%APK_OUT_DIR%"
if errorlevel 1 (
  echo [ERR] mkdir failed: %APK_OUT_DIR%
  exit /b 1
)
call :require_path "%APK%" "Gradle APK not found"
if errorlevel 1 exit /b 1
copy /y "%APK%" "%OUT%" >nul
if errorlevel 1 (
  echo [ERR] copy failed
  exit /b 1
)
call :require_path "%OUT%" "output apk missing after copy"
if errorlevel 1 exit /b 1
call :require_file_size "%OUT%" "output apk is empty"
if errorlevel 1 exit /b 1
for %%F in ("%OUT%") do echo [OK] %OUT% size=%%~zF bytes
exit /b 0

:verify_apk_badging
del "%BADGE%" >nul 2>&1
"%AAPT%" dump badging "%OUT%" > "%BADGE%" 2>&1
if errorlevel 1 (
  echo [ERR] aapt badging failed
  call :show_badge
  exit /b 1
)
findstr /b /c:"package:" "%BADGE%" | findstr /c:"name='%APP_ID%'" >nul
if errorlevel 1 (
  echo [ERR] package id mismatch, expected %APP_ID%
  call :show_badge
  exit /b 1
)
findstr /b /c:"launchable-activity:" "%BADGE%" >nul
if errorlevel 1 (
  echo [ERR] launchable-activity missing in apk
  call :show_badge
  exit /b 1
)
findstr /b /c:"package:" /c:"application-label:" /c:"launchable-activity:" "%BADGE%"
if errorlevel 1 (
  echo [ERR] aapt badging verification failed
  call :show_badge
  exit /b 1
)
echo [OK]
exit /b 0

:show_badge
if exist "%BADGE%" type "%BADGE%"
exit /b 0

:cleanup
del "%BADGE%" >nul 2>&1
exit /b 0

REM ============================================================================
REM main
REM ============================================================================

:run

set "STEP_N=1"
call :step_banner "Java"
call :setup_java
if errorlevel 1 goto :fail

set "STEP_N=2"
call :step_banner "Android SDK"
call :require_path "%SDK%\platforms\android-25\android.jar" "android-25 SDK missing"
if errorlevel 1 goto :fail
call :require_path "%AAPT%" "build-tools 30.0.2 missing"
if errorlevel 1 goto :fail
echo [OK]

set "STEP_N=3"
call :step_banner "rosjava local Maven repo"
call :check_rosjava_repo
if errorlevel 1 goto :fail

set "STEP_N=4"
call :step_banner "project layout and package id support"
call :check_appid_support
if errorlevel 1 goto :fail

set "STEP_N=5"
call :step_banner "project local.properties"
call :write_local_properties
if errorlevel 1 goto :fail

set "STEP_N=6"
call :step_banner "Gradle build"
call :run_gradle
if errorlevel 1 goto :fail

set "STEP_N=7"
call :step_banner "collect APK"
call :collect_apk
if errorlevel 1 goto :fail

set "STEP_N=8"
call :step_banner "verify APK package and launcher"
call :verify_apk_badging
if errorlevel 1 goto :fail

call :cleanup
echo.
echo ============================================================
echo [OK] RobotCA build complete
echo [OK] package=%APP_ID%
echo [OK] apk=%OUT%
echo ============================================================
exit /b 0

:fail
call :cleanup
exit /b 1
