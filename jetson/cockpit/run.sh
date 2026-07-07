#!/usr/bin/env bash
set -eo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
set +u
# shellcheck disable=SC1090
source "$ROS_SETUP"
set -u

exec python3 app.py
