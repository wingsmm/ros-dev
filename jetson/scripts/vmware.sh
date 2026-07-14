#!/usr/bin/env bash
# jetson/scripts/vmware.sh
# Windows / Git Bash → ssh/rsync → VMware Ubuntu（cockpit 观测端）
#
# 读取 jetson/scripts/.env 中的 VMWARE_* 变量：
#   VMWARE_HOST / VMWARE_USER / VMWARE_PORT / VMWARE_PASSWORD / VMWARE_KEY
# Jetson 侧连通性检测读取同文件 HOST（默认 172.0.0.82）
#
# 远端目录约定：
#   本地 jetson/cockpit/  →  远端 ~/ros-dev/jetson/cockpit/
#
# 用法：
#   vmware.sh                         交互式 ssh
#   vmware.sh probe                   VM 只读体检
#   vmware.sh push [--yes]            dry-run / 真推送 cockpit
#   vmware.sh deploy                  push --yes + 远端修 CRLF
#   vmware.sh verify                  VM↔Jetson 网络 + ROS2 topic/hz
#   vmware.sh rviz                    远端启动 RViz2（需 VM 有图形）
#   vmware.sh <任意远端命令...>       单条命令

set -euo pipefail

REPO_JETSON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a

: "${VMWARE_HOST:?VMWARE_HOST required in $ENV_FILE}"
: "${VMWARE_USER:?VMWARE_USER required in $ENV_FILE}"
VMWARE_PORT="${VMWARE_PORT:-22}"

# Jetson（点云源）— 用于 verify
JETSON_HOST="${HOST:-}"
ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"

LOCAL_COCKPIT="$REPO_JETSON_DIR/cockpit"
REMOTE_ROOT="${VMWARE_REMOTE_ROOT:-ros-dev}"
REMOTE_COCKPIT="${REMOTE_ROOT}/jetson/cockpit"

HOST="$VMWARE_HOST"
USER="$VMWARE_USER"
PORT="$VMWARE_PORT"
PASSWORD="${VMWARE_PASSWORD:-}"
KEY="${VMWARE_KEY:-}"

ssh_opts=(-p "$PORT" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8)

_auth_prefix=()
if [[ -n "${KEY:-}" && -f "$KEY" ]]; then
  ssh_opts+=(-i "$KEY")
elif [[ -n "${PASSWORD:-}" ]]; then
  command -v sshpass >/dev/null || {
    echo "need sshpass for password auth: sudo apt install -y sshpass" >&2
    exit 3
  }
  _auth_prefix=(sshpass -p "$PASSWORD")
fi

ssh_run() {
  "${_auth_prefix[@]}" ssh "${ssh_opts[@]}" "$USER@$HOST" "$@"
}

_rsync_ssh_cmd() {
  local ssh_cmd="ssh ${ssh_opts[*]}"
  [[ ${#_auth_prefix[@]} -gt 0 ]] && ssh_cmd="sshpass -p $PASSWORD $ssh_cmd"
  printf '%s' "$ssh_cmd"
}

_cockpit_excludes=(
  --exclude='.env'
  --exclude='.venv/'
  --exclude='__pycache__/'
  --exclude='*.pyc'
  --exclude='logs/*'
  --exclude='.DS_Store'
)

usage() {
  cat <<USAGE
Usage:
  vmware.sh                         interactive ssh to VM
  vmware.sh probe                   inspect VM (OS/ROS/disk/~/ros-dev)
  vmware.sh push [--yes]            sync local jetson/cockpit -> ~/${REMOTE_COCKPIT}
  vmware.sh deploy                  push --yes + fix CRLF on remote .sh
  vmware.sh verify                  ping Jetson + ros2 topic list/hz on VM
  vmware.sh rviz                    start RViz2 on VM (unilidar.rviz)
  vmware.sh <remote command>        run one command on VM

Env (jetson/scripts/.env):
  VMWARE_HOST / VMWARE_USER / VMWARE_PORT / VMWARE_PASSWORD / VMWARE_KEY
  HOST (Jetson, for verify)         default from .env
  ROS_DOMAIN_ID                     default 0
  VMWARE_REMOTE_ROOT                default ros-dev
USAGE
}

remote_probe() {
  ssh_run "
    set +e
    echo '== vm host =='
    hostname; uname -a; uptime
    echo '== os =='
    grep -E '^(NAME|VERSION)=' /etc/os-release
    echo '== disk =='
    df -h / /home 2>/dev/null
    echo '== ros =='
    ls /opt/ros 2>/dev/null
    command -v ros2 && ros2 --version 2>/dev/null | head -1
    command -v rviz2 && echo 'rviz2: ok'
    echo '== ~/ ${REMOTE_ROOT} =='
    ls -la ~/${REMOTE_ROOT} 2>/dev/null
    ls -la ~/${REMOTE_COCKPIT} 2>/dev/null | head -20
    echo '== display =='
    echo DISPLAY=\${DISPLAY:-<empty>}
    echo WAYLAND_DISPLAY=\${WAYLAND_DISPLAY:-<empty>}
  "
}

push_cockpit() {
  command -v rsync >/dev/null || { echo "need rsync" >&2; exit 3; }
  local yes="${1:-}"
  [[ -d "$LOCAL_COCKPIT" ]] || { echo "missing $LOCAL_COCKPIT" >&2; exit 2; }

  local mode="dry-run" flag=(-n)
  if [[ "$yes" == "--yes" ]]; then
    mode="write"
    flag=()
    echo ">>> push $LOCAL_COCKPIT/ -> $USER@$HOST:~/${REMOTE_COCKPIT}/ (write, no --delete)"
    ssh_run "mkdir -p ~/${REMOTE_COCKPIT}"
  else
    echo ">>> push $LOCAL_COCKPIT/ -> $USER@$HOST:~/${REMOTE_COCKPIT}/ (dry-run, add --yes)"
  fi

  rsync -av "${flag[@]}" "${_cockpit_excludes[@]}" \
    -e "$(_rsync_ssh_cmd)" \
    "$LOCAL_COCKPIT/" \
    "$USER@$HOST:~/${REMOTE_COCKPIT}/"
}

fix_remote_crlf() {
  ssh_run "
    set -e
    if [[ -d ~/${REMOTE_COCKPIT}/scripts ]]; then
      # Use \$'\\r' so remote bash expands a real CR (plain sed '\\r' is unreliable).
      find ~/${REMOTE_COCKPIT}/scripts -type f -name '*.sh' -print0 |
        xargs -0 -r sed -i \$'s/\\r\$//'
      chmod +x ~/${REMOTE_COCKPIT}/scripts/*.sh 2>/dev/null || true
      echo '[OK] fixed CRLF on remote cockpit scripts'
    fi
  "
}

deploy_cockpit() {
  push_cockpit --yes
  fix_remote_crlf
  echo "[OK] cockpit deployed to ~/${REMOTE_COCKPIT}"
}

verify_lidar() {
  if [[ -z "${JETSON_HOST:-}" ]]; then
    echo "[WARN] HOST (Jetson) not set in .env; skip ping" >&2
  else
    echo "== ping Jetson ${JETSON_HOST} from VM =="
    ssh_run "ping -c 3 -W 2 ${JETSON_HOST}" || {
      echo "[FAIL] VM cannot ping Jetson ${JETSON_HOST}" >&2
      exit 10
    }
  fi

  echo "== ROS2 on VM (ROS_DOMAIN_ID=${ROS_DOMAIN_ID}) =="
  ssh_run "
    set -e
    set +u
    source /opt/ros/humble/setup.bash
    set -u
    export ROS_DOMAIN_ID=${ROS_DOMAIN_ID}

    echo '--- ros2 topic list ---'
    ros2 topic list 2>&1 | tee /tmp/vmware_verify_topics.txt

    if ! grep -qx '/unilidar/cloud' /tmp/vmware_verify_topics.txt; then
      echo '[FAIL] /unilidar/cloud not visible on VM DDS' >&2
      echo 'hint: ensure Jetson unitree_lidar_ros2 is running and same ROS_DOMAIN_ID' >&2
      exit 20
    fi
    if ! grep -qx '/unilidar/imu' /tmp/vmware_verify_topics.txt; then
      echo '[WARN] /unilidar/imu not visible (cloud ok)' >&2
    fi

    echo '--- /unilidar/cloud hz (12s) ---'
    timeout 12 ros2 topic hz /unilidar/cloud 2>&1 | tail -6 || true

    echo '--- /unilidar/imu hz (8s) ---'
    timeout 8 ros2 topic hz /unilidar/imu 2>&1 | tail -6 || true

    echo '[OK] verify done'
  "
}

start_rviz() {
  ssh_run "
    set -e
    cd ~/${REMOTE_COCKPIT}
    if [[ ! -f config/unilidar.rviz ]]; then
      echo '[ERR] missing ~/${REMOTE_COCKPIT}/config/unilidar.rviz (run: vmware.sh deploy)' >&2
      exit 2
    fi
    set +u
    source /opt/ros/humble/setup.bash
    set -u
    export ROS_DOMAIN_ID=${ROS_DOMAIN_ID}
    echo '[OK] rviz2 -d config/unilidar.rviz  (close window to exit)'
    exec rviz2 -d config/unilidar.rviz
  "
}

case "${1:-}" in
  "")
    if [[ ${#_auth_prefix[@]} -gt 0 ]]; then
      exec "${_auth_prefix[@]}" ssh "${ssh_opts[@]}" "$USER@$HOST"
    else
      exec ssh "${ssh_opts[@]}" "$USER@$HOST"
    fi
    ;;
  help|-h|--help)
    usage
    ;;
  probe)
    remote_probe
    ;;
  push)
    shift
    push_cockpit "${1:-}"
    ;;
  deploy)
    deploy_cockpit
    ;;
  verify|verify-lidar|lidar)
    verify_lidar
    ;;
  rviz)
    start_rviz
    ;;
  *)
    ssh_run "$*"
    ;;
esac
