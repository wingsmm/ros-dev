#!/usr/bin/env bash
# bridge_stack.sh — start/stop/status/logs for cmd_vel_car_web_bridge
# Lives on Jetson at ~/qt/ros2_ws/scripts/bridge_stack.sh (synced from
# jetson/mirror/ros2_ws/scripts/ by jetson.sh push).
#
# Modeled after xtark/scripts/*_stack.sh: PID + log + owner file in
# ~/qt_logs/bridge_stack/. Foreground SSH only sends single-line
# start/stop/status verbs; long-running node lives in nohup + PID file.
#
# Usage (on Jetson OR via jetson.sh <cmd>):
#   bridge_stack.sh start          # nohup ros2 run cmd_vel_car_web_bridge bridge
#   bridge_stack.sh stop
#   bridge_stack.sh status
#   bridge_stack.sh logs [-f]      # tail log file (-f follow)
#   bridge_stack.sh verify         # start + send 5 twists + stop, print log
#   bridge_stack.sh restart
#
# Dry-run stage: does NOT call car_web. Just prints CONTROL_ACTION=*.

set -euo pipefail

STACK=bridge_stack
LOG_ROOT="${QT_LOGS_ROOT:-$HOME/qt_logs}"
LOG_DIR="$LOG_ROOT/$STACK"
PID_FILE="$LOG_DIR/bridge.pid"
LOG_FILE="$LOG_DIR/bridge.log"
OWNER_FILE="$LOG_DIR/owner"

ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="$HOME/qt/ros2_ws/install/setup.bash"

# ---------- helpers ----------

_ensure_dirs() {
  mkdir -p "$LOG_DIR"
}

_source_ros() {
  # ROS setup.bash references AMENT_TRACE_SETUP_FILES and friends
  # without setting them first, which explodes under `set -u`.
  # Turn nounset off just around the sourcing, keep everything else strict.
  set +u
  # shellcheck disable=SC1090
  source "$ROS_SETUP"
  if [ ! -f "$WS_SETUP" ]; then
    set -u
    echo "[ERR] ws not built: $WS_SETUP missing (run colcon build first)" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$WS_SETUP"
  set -u
}

_pid_alive() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

_read_pid() {
  [ -f "$PID_FILE" ] && cat "$PID_FILE" || true
}

_is_running() {
  local pid
  pid="$(_read_pid)"
  _pid_alive "$pid"
}

# ---------- commands ----------

cmd_start() {
  _ensure_dirs
  if _is_running; then
    echo "[INFO] bridge already running pid=$(_read_pid)"
    return 0
  fi
  # Clean stale pid file if any
  rm -f "$PID_FILE"

  _source_ros

  # Fresh log per start; append could be nicer, but for dry-run stage
  # a clean log makes eyeballing verify runs easier.
  : > "$LOG_FILE"

  # nohup + disown so it survives SSH session close.
  nohup ros2 run cmd_vel_car_web_bridge bridge >>"$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  echo "$STACK" > "$OWNER_FILE"
  disown "$pid" 2>/dev/null || true

  # Wait briefly for node banner so `start` fails loudly if the node
  # dies on import (rclpy missing, wrong domain id, etc).
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if ! _pid_alive "$pid"; then
      echo "[ERR] bridge exited during startup"
      echo "--- log tail ---"
      tail -n 40 "$LOG_FILE" || true
      rm -f "$PID_FILE" "$OWNER_FILE"
      exit 1
    fi
    if grep -q 'cmd_vel_car_web_bridge started' "$LOG_FILE" 2>/dev/null; then
      break
    fi
    sleep 0.3
  done

  echo "[OK] bridge started pid=$pid log=$LOG_FILE"
}

cmd_stop() {
  local pid
  pid="$(_read_pid)"
  if _pid_alive "$pid"; then
    echo "[INFO] stopping bridge pid=$pid"
    kill "$pid" 2>/dev/null || true
    local i
    for i in 1 2 3 4 5 6 7 8 9 10; do
      _pid_alive "$pid" || break
      sleep 0.2
    done
    if _pid_alive "$pid"; then
      echo "[WARN] SIGTERM ignored, sending SIGKILL"
      kill -9 "$pid" 2>/dev/null || true
    fi
  else
    echo "[INFO] bridge not running"
  fi

  # Sweep orphan bridge processes that share our install path.
  # Match the exact installed executable to avoid killing unrelated
  # ROS2 nodes; also skips our own shell pid via pgrep's default.
  local pattern="$HOME/qt/ros2_ws/install/cmd_vel_car_web_bridge/lib/cmd_vel_car_web_bridge/bridge"
  local orphans
  orphans="$(pgrep -f "$pattern" || true)"
  if [ -n "$orphans" ]; then
    echo "[INFO] sweeping bridge orphans: $orphans"
    # shellcheck disable=SC2086
    kill $orphans 2>/dev/null || true
    sleep 0.4
    orphans="$(pgrep -f "$pattern" || true)"
    if [ -n "$orphans" ]; then
      echo "[WARN] SIGTERM ignored by $orphans, SIGKILL"
      # shellcheck disable=SC2086
      kill -9 $orphans 2>/dev/null || true
    fi
  fi

  rm -f "$PID_FILE" "$OWNER_FILE"
  echo "[OK] bridge stopped"
}

cmd_status() {
  local pid
  pid="$(_read_pid)"
  if _pid_alive "$pid"; then
    echo "state=running pid=$pid"
  else
    echo "state=stopped"
  fi
  echo "log=$LOG_FILE"
  echo "pid_file=$PID_FILE"
  echo "owner_file=$OWNER_FILE"
  # Also show whether the ROS topic side is alive, so remote 'status'
  # can catch cases where the process is up but /cmd_vel isn't wired.
  if _pid_alive "$pid" && [ -f "$WS_SETUP" ]; then
    _source_ros
    echo "--- ros2 topic list (grep) ---"
    ros2 topic list 2>/dev/null | grep -E '^/(cmd_vel|vehicle/control_action)$' || echo "(no relevant topics yet)"
  fi
}

cmd_logs() {
  if [ ! -f "$LOG_FILE" ]; then
    echo "[INFO] no log file yet: $LOG_FILE"
    return 0
  fi
  case "${1:-}" in
    -f|--follow) tail -f "$LOG_FILE" ;;
    *)           tail -n "${1:-80}" "$LOG_FILE" ;;
  esac
}

cmd_restart() {
  cmd_stop || true
  sleep 0.5
  cmd_start
}

# End-to-end dry-run verify: start bridge, publish 5 Twists via
# `ros2 topic pub --once`, tail the log, then stop.
cmd_verify() {
  cmd_start
  _source_ros

  # Give discovery a beat before publishing.
  sleep 1

  _send() {
    local name="$1" lx="$2" az="$3"
    echo "--- send $name lx=$lx az=$az ---"
    ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
      "{linear: {x: $lx, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: $az}}" \
      >/dev/null
    sleep 0.4
  }

  _send FORWARD    1.0  0.0
  _send BACKWARD  -1.0  0.0
  _send TURN_LEFT  0.0  1.0
  _send TURN_RIGHT 0.0 -1.0
  _send STOP       0.0  0.0

  sleep 0.5

  echo "===== bridge log ====="
  cat "$LOG_FILE"
  echo "===== end ====="

  cmd_stop
}

# ---------- dispatch ----------

case "${1:-}" in
  start)   shift; cmd_start   "$@" ;;
  stop)    shift; cmd_stop    "$@" ;;
  status)  shift; cmd_status  "$@" ;;
  logs)    shift; cmd_logs    "$@" ;;
  restart) shift; cmd_restart "$@" ;;
  verify)  shift; cmd_verify  "$@" ;;
  ""|-h|--help)
    cat <<USAGE
bridge_stack.sh — cmd_vel_car_web_bridge lifecycle (dry-run)

Commands:
  start           start bridge in background (nohup + PID file)
  stop            stop and clean PID / owner
  status          state + PID + relevant topic presence
  logs [N|-f]     tail last N lines (default 80) or follow
  restart         stop + start
  verify          start + send 5 Twists + print log + stop (end-to-end DDS test)
USAGE
    ;;
  *) echo "unknown: $1" >&2; exit 2 ;;
esac
