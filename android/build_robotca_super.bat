@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=alt"
set "JDK=%ROOT%tools\jdk8"
set "SDK=D:\ProgramData\Android\sdk"
set "ROSJAVA=%ROOT%tools\rosjava_mvn_repo"
set "APP=%ROOT%RobotCA-master\RobotCA-master\src\android_foo\control_app"
set "APK=%APP%\build\outputs\apk\control_app-debug.apk"
set "GRADLE_ARGS=--no-daemon assembleDebug"
set "OUT=%ROOT%xtark-control-alt-debug.apk"
set "APP_ID=cn.xtark.robotca"
set "VERSION_NAME=1.0-xtark-alt"
set "GRADLE_ARGS=--no-daemon assembleDebug -PappId=cn.xtark.robotca -PappVersionName=1.0-xtark-alt"

if /i "%MODE%"=="orig" (
  set "OUT=%ROOT%xtark-control-debug.apk"
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

echo.
echo ------------------------------------------------------------
echo [STEP] Java
echo ------------------------------------------------------------
if not exist "%JDK%\bin\java.exe" (
  echo [ERR] JDK8 missing: %JDK%\bin\java.exe
  exit /b 1
)
"%JDK%\bin\java.exe" -version
if errorlevel 1 (
  echo [ERR] JDK8 cannot run
  exit /b 1
)
set "JAVA_HOME=%JDK%"
set "PATH=%JDK%\bin;%SDK%\platform-tools;%PATH%"
echo [OK]

echo.
echo ------------------------------------------------------------
echo [STEP] Android SDK
echo ------------------------------------------------------------
if not exist "%SDK%\platforms\android-25\android.jar" (
  echo [ERR] android-25 SDK missing: %SDK%\platforms\android-25
  exit /b 1
)
if not exist "%SDK%\build-tools\30.0.2\aapt.exe" (
  echo [ERR] build-tools 30.0.2 missing: %SDK%\build-tools\30.0.2
  exit /b 1
)
echo [OK]

echo.
echo ------------------------------------------------------------
echo [STEP] rosjava local Maven repo
echo ------------------------------------------------------------
if not exist "%ROSJAVA%\.git" (
  echo [ERR] rosjava repo missing: %ROSJAVA%
  echo       run fetch_rosjava.bat first
  exit /b 1
)
if not exist "%ROSJAVA%\org\ros\android_core\android_10\0.2.1" (
  echo [ERR] missing android_10 0.2.1 in rosjava repo
  exit /b 1
)
if not exist "%ROSJAVA%\org\ros\android_core\android_15\0.2.1" (
  echo [ERR] missing android_15 0.2.1 in rosjava repo
  exit /b 1
)
if not exist "%ROSJAVA%\com\github\rosjava\android_extras\gingerbread\0.2.0" (
  echo [ERR] missing gingerbread 0.2.0 in rosjava repo
  exit /b 1
)
if not exist "%ROSJAVA%\org\ros\rosjava_messages\tf2_msgs\0.5.13" (
  echo [ERR] missing tf2_msgs 0.5.13 in rosjava repo
  exit /b 1
)
echo [OK]

echo.
echo ------------------------------------------------------------
echo [STEP] Project layout and package id support
echo ------------------------------------------------------------
if not exist "%APP%\gradlew.bat" (
  echo [ERR] gradlew.bat missing: %APP%
  exit /b 1
)
findstr /c:"applicationId project.hasProperty('appId')" "%APP%\build.gradle" >nul
if errorlevel 1 (
  echo [ERR] build.gradle does not support -PappId
  exit /b 1
)
echo [OK]

echo.
echo ------------------------------------------------------------
echo [STEP] Project local.properties
echo ------------------------------------------------------------
>"%APP%\local.properties" echo sdk.dir=D\:\\ProgramData\\Android\\sdk
echo [OK]

echo.
echo ------------------------------------------------------------
echo [STEP] Gradle build
echo ------------------------------------------------------------
cd /d "%APP%"
call "%APP%\gradlew.bat" %GRADLE_ARGS%
if errorlevel 1 (
  echo [ERR] Gradle build failed
  exit /b 1
)
echo [OK]

echo.
echo ------------------------------------------------------------
echo [STEP] Collect APK
echo ------------------------------------------------------------
if not exist "%APK%" (
  echo [ERR] APK not found: %APK%
  exit /b 1
)
copy /y "%APK%" "%OUT%" >nul
if errorlevel 1 (
  echo [ERR] copy failed
  exit /b 1
)
echo [OK] %OUT%

echo.
echo ------------------------------------------------------------
echo [STEP] Verify APK package and launcher
echo ------------------------------------------------------------
set "AAPT=%SDK%\build-tools\30.0.2\aapt.exe"
"%AAPT%" dump badging "%OUT%" | findstr /b /c:"package:" /c:"application-label:" /c:"launchable-activity:"
if errorlevel 1 (
  echo [ERR] aapt badging failed
  exit /b 1
)

echo.
echo ============================================================
echo [OK] RobotCA build complete
echo [OK] package=%APP_ID%
echo [OK] apk=%OUT%
echo ============================================================
exit /b 0
