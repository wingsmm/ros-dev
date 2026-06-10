@echo off
setlocal EnableExtensions

set "PLINK=C:\Program Files\PuTTY\plink.exe"
set "HOSTKEY=SHA256:hrGvBYXQfk9JH6fq71t0BYZEoulJ5WjZomhk5NlkLOY"

"%PLINK%" -ssh xtark@192.168.1.169 -pw xtark -batch -hostkey "%HOSTKEY%" "/home/xtark/ros_ws/scripts/run_android.sh start"
exit /b %ERRORLEVEL%
