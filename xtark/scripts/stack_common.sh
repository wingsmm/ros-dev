#!/usr/bin/env bash
# Shared ownership and conflict checks for android_stack / qt_stack.
# shellcheck shell=bash

XTARK_LOGS_ROOT="${XTARK_LOGS_ROOT:-$HOME/xtark_logs}"

stack_log_dir() {
  echo "$XTARK_LOGS_ROOT/$1"
}

stack_pid_dir() {
  echo "$(stack_log_dir "$1")/pids"
}

stack_owner_file() {
  echo "$(stack_log_dir "$1")/owner"
}

stack_is_listening() {
  local port="$1"
  (ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null) | grep -q ":${port}"
}

stack_pid_alive() {
  local f="$1"
  [ -f "$f" ] || return 1
  local pid
  pid="$(cat "$f")"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

stack_write_pid() {
  local stack="$1"
  local name="$2"
  local pid="$3"
  mkdir -p "$(stack_pid_dir "$stack")"
  echo "$pid" >"$(stack_pid_dir "$stack")/$name.pid"
}

stack_stop_pid() {
  local stack="$1"
  local name="$2"
  local f
  f="$(stack_pid_dir "$stack")/$name.pid"
  if stack_pid_alive "$f"; then
    local pid
    pid="$(cat "$f")"
    echo "[INFO] stop $name pid=$pid"
    kill "$pid" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$f"
}

stack_claim_owner() {
  local stack="$1"
  mkdir -p "$(stack_log_dir "$stack")" "$(stack_pid_dir "$stack")"
  echo "$stack" >"$(stack_owner_file "$stack")"
}

stack_release_owner() {
  rm -f "$(stack_owner_file "$1")"
}

stack_qt_sidecars_present() {
  if stack_is_listening 8765; then
    return 0
  fi
  if pgrep -f 'json_base_adapter_node.py|json_base_adapter.launch' >/dev/null 2>&1; then
    return 0
  fi
  if pgrep -f 'rf2o_odom_laser.launch|rf2o_laser_odometry' >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

stack_qt_processes_alive() {
  local pid_dir name
  pid_dir="$(stack_pid_dir qt_stack)"
  for name in roscore bringup json camera web_video rgb_relay depth_camera depth_preview rf2o rosbag; do
    if stack_pid_alive "$pid_dir/$name.pid"; then
      return 0
    fi
  done
  if stack_qt_sidecars_present; then
    return 0
  fi
  return 1
}

stack_android_processes_alive() {
  local pattern
  for pattern in \
    'rosrun gmapping slam_gmapping' \
    'slam_gmapping scan:=' \
    'online_slam_move_base.launch' \
    '[ /]move_base([ ]|$)' \
    'run_android_nav_speed_sync' \
    'robot_pose_in_map.launch' \
    'robot_pose_in_map_publisher'; do
    if pgrep -f "$pattern" >/dev/null 2>&1; then
      return 0
    fi
  done
  if stack_qt_sidecars_present; then
    return 1
  fi
  if pgrep -f 'roslaunch xtark_driver xtark_bringup.launch' >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

stack_pc_processes_alive() {
  local pid_dir name
  pid_dir="$(stack_pid_dir pc_stack)"
  for name in roscore bringup camera rgb_relay depth_camera; do
    if stack_pid_alive "$pid_dir/$name.pid"; then
      return 0
    fi
  done
  return 1
}

stack_stack_processes_alive() {
  case "$1" in
    qt_stack) stack_qt_processes_alive ;;
    android_stack) stack_android_processes_alive ;;
    pc_stack) stack_pc_processes_alive ;;
    *) return 1 ;;
  esac
}

stack_refresh_owner() {
  local stack="$1"
  if ! [ -f "$(stack_owner_file "$stack")" ]; then
    return 0
  fi
  if stack_stack_processes_alive "$stack"; then
    return 0
  fi
  echo "[WARN] removing stale owner for $stack (no live processes)"
  stack_release_owner "$stack"
}

stack_refresh_all_owners() {
  stack_refresh_owner android_stack
  stack_refresh_owner qt_stack
  stack_refresh_owner pc_stack
}

stack_owner_running() {
  local stack="$1"
  stack_refresh_owner "$stack"
  [ -f "$(stack_owner_file "$stack")" ]
}

stack_qt_is_active() {
  stack_refresh_owner qt_stack
  if stack_owner_running qt_stack; then
    return 0
  fi
  stack_qt_processes_alive
}

stack_assert_android_stop_safe() {
  stack_refresh_all_owners
  if stack_qt_is_active; then
    echo "[ERR] qt_stack is active (owner file and/or Qt processes present)"
    echo "      Run: ~/ros_ws/scripts/qt_stack.sh stop"
    echo "      Refusing android_stack.sh stop to avoid killing Qt roscore/bringup/camera/JSON."
    exit 1
  fi
}

stack_other_owner() {
  local my_stack="$1"
  local other
  for other in android_stack qt_stack pc_stack; do
    [ "$other" = "$my_stack" ] && continue
    if stack_owner_running "$other"; then
      echo "$other"
      return 0
    fi
  done
  return 1
}

stack_assert_no_other_owner() {
  local my_stack="$1"
  local other
  stack_refresh_all_owners
  if other="$(stack_other_owner "$my_stack")"; then
    echo "[ERR] $other is active (owner: $(stack_owner_file "$other"))"
    echo "      Stop it first: ~/ros_ws/scripts/${other}.sh stop"
    exit 1
  fi
}

stack_assert_port_owned_or_free() {
  local stack="$1"
  local pid_name="$2"
  local port="$3"
  local label="$4"
  if ! stack_is_listening "$port"; then
    return 0
  fi
  local pid_file
  pid_file="$(stack_pid_dir "$stack")/$pid_name.pid"
  if stack_pid_alive "$pid_file"; then
    return 0
  fi
  echo "[ERR] ${label} port ${port} is in use but not owned by ${stack}"
  echo "      Stop conflicting stacks first (android_stack.sh / qt_stack.sh)"
  (ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | grep ":${port}" || true
  exit 1
}

stack_assert_process_owned_or_absent() {
  local stack="$1"
  local pid_name="$2"
  local pattern="$3"
  local label="$4"
  if ! pgrep -f "$pattern" >/dev/null 2>&1; then
    return 0
  fi
  local pid_file
  pid_file="$(stack_pid_dir "$stack")/$pid_name.pid"
  if stack_pid_alive "$pid_file"; then
    return 0
  fi
  echo "[ERR] ${label} already running but not owned by ${stack}"
  echo "      Pattern: $pattern"
  pgrep -af "$pattern" || true
  exit 1
}

stack_assert_no_qt_sidecars() {
  if stack_is_listening 8765; then
    echo "[ERR] JSON gateway port 8765 is in use (qt_stack sidecar)"
    echo "      Stop qt_stack.sh first"
    exit 1
  fi
  if pgrep -f 'json_base_adapter_node.py|json_base_adapter.launch' >/dev/null 2>&1; then
    echo "[ERR] json_base_adapter is running (qt_stack sidecar)"
    echo "      Stop qt_stack.sh first"
    exit 1
  fi
  if pgrep -f 'rf2o_odom_laser.launch|rf2o_laser_odometry' >/dev/null 2>&1; then
    echo "[ERR] rf2o / odom_laser sidecar is running (qt_stack)"
    echo "      Stop qt_stack.sh first"
    exit 1
  fi
}

stack_assert_no_android_nav() {
  local pattern
  for pattern in \
    'rosrun gmapping slam_gmapping' \
    'slam_gmapping scan:=' \
    'online_slam_move_base.launch' \
    '[ /]move_base([ ]|$)' \
    'robot_pose_in_map.launch' \
    'robot_pose_in_map_publisher' \
    'run_android_nav_speed_sync'; do
    if pgrep -f "$pattern" >/dev/null 2>&1; then
      echo "[ERR] Android navigation process detected ($pattern)"
      echo "      Stop android_stack.sh first"
      pgrep -af "$pattern" || true
      exit 1
    fi
  done
}
