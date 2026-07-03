@echo off
rem Shared PuTTY/SCP settings for xtark Windows remote helpers.
rem Call from sibling .bat scripts: call "%~dp0_xtark_remote_env.bat"
rem Environment variables below override defaults when already set.

if not defined PLINK set "PLINK=C:\Program Files\PuTTY\plink.exe"
if not defined PSCP set "PSCP=C:\Program Files\PuTTY\pscp.exe"
if not defined XTARK_HOST set "XTARK_HOST=192.168.1.169"
if not defined XTARK_USER set "XTARK_USER=xtark"
if not defined XTARK_PASSWORD set "XTARK_PASSWORD=xtark"
if not defined XTARK_HOSTKEY set "XTARK_HOSTKEY=SHA256:hrGvBYXQfk9JH6fq71t0BYZEoulJ5WjZomhk5NlkLOY"

if not defined XTARK_VM_HOST set "XTARK_VM_HOST=192.168.1.154"
if not defined XTARK_VM_HOSTKEY set "XTARK_VM_HOSTKEY=SHA256:PtzWE2T7/bY7TdqIzyfTc7bJuifo0PjA4BEaorV0odA"

set "XTARK_REMOTE=%XTARK_USER%@%XTARK_HOST%"
set "XTARK_VM_REMOTE=%XTARK_USER%@%XTARK_VM_HOST%"
set "XTARK_REMOTE_WS=/home/xtark/ros_ws"
set "XTARK_REMOTE_SCRIPTS=%XTARK_REMOTE_WS%/scripts"
set "XTARK_REMOTE_TOOLS=%XTARK_REMOTE_WS%/tools"
