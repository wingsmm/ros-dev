#!/usr/bin/env bash
# jetson/scripts/jetson.sh
# Windows → WSL/Git Bash → ssh/rsync → Jetson。
#
# 目录约定：
#   本地 jetson/mirror/  ↔  远端 ~/qt/
#   两边双向同步；本地是主开发目录。
#
# 用法：
#   jetson.sh                       交互式 ssh（默认）
#   jetson.sh probe                 只读探测：OS/CUDA/ROS/磁盘
#   jetson.sh pull [subdir]         远端 ~/qt/[subdir]/ → 本地 jetson/mirror/[subdir]/
#                                    不传 subdir = 整个 ~/qt/
#   jetson.sh push <subdir>         dry-run：预览本地 → 远端 会写什么
#   jetson.sh push <subdir> --yes   真写；默认不带 --delete
#   jetson.sh <任意远端命令...>     单条命令
#
# .env（jetson/scripts/.env）需要：
#   HOST=172.0.0.52          # 默认 profile（不写 profile 时用它）
#   USER=nvidia
#   PORT=22
#   PASSWORD=nvidia          # 可选
#   KEY=/path/to/id_ed25519  # 可选，优先
#
# 可选：同一份 .env 里维护多套 profile（向后兼容，不影响默认 HOST/USER）
#   HOST_VM=172.0.0.87
#   USER_VM=wingsmm
#   PORT_VM=22
#   PASSWORD_VM=mm830830
#   KEY_VM=/path/to/id_ed25519
#
# 选择 profile 的方式（二选一）：
#   1) 环境变量：JETSON_PROFILE=vm jetson.sh probe
#   2) 参数：    jetson.sh --profile vm probe

set -euo pipefail

REPO_JETSON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a

PROFILE="${JETSON_PROFILE:-}"
if [[ "${1:-}" == "--profile" ]]; then
  PROFILE="${2:-}"
  shift 2
elif [[ "${1:-}" == "--profile="* ]]; then
  PROFILE="${1#--profile=}"
  shift 1
fi

_upper() { printf '%s' "${1^^}"; }
_get_profile_var() {
  local key="$1" profile="$2"
  local up="$(_upper "$profile")"
  local name="${key}_${up}"
  # shellcheck disable=SC2163
  if [[ -n "${!name:-}" ]]; then
    printf '%s' "${!name}"
    return 0
  fi
  return 1
}

if [[ -n "${PROFILE:-}" ]]; then
  # profile 存在时，优先读取 HOST_<PROFILE>/USER_<PROFILE>/...，缺省则回退到默认 HOST/USER/...
  HOST="$(_get_profile_var HOST "$PROFILE" || printf '%s' "${HOST:-}")"
  USER="$(_get_profile_var USER "$PROFILE" || printf '%s' "${USER:-}")"
  PORT="$(_get_profile_var PORT "$PROFILE" || printf '%s' "${PORT:-22}")"
  PASSWORD="$(_get_profile_var PASSWORD "$PROFILE" || printf '%s' "${PASSWORD:-}")"
  KEY="$(_get_profile_var KEY "$PROFILE" || printf '%s' "${KEY:-}")"
else
  : "${HOST:?HOST required in .env}"
  : "${USER:?USER required in .env}"
  PORT="${PORT:-22}"
fi

: "${HOST:?HOST required (profile=${PROFILE:-default})}"
: "${USER:?USER required (profile=${PROFILE:-default})}"

# 本地镜像根（对应远端 ~/qt/）
LOCAL_QT="$REPO_JETSON_DIR/mirror"
REMOTE_ROS2_WS="qt/ros2_ws"

ssh_opts=(-p "$PORT" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8)

_auth_prefix=()
if [[ -n "${KEY:-}" && -f "$KEY" ]]; then
  ssh_opts+=(-i "$KEY")
elif [[ -n "${PASSWORD:-}" ]]; then
  command -v sshpass >/dev/null || { echo "need sshpass: sudo apt install -y sshpass" >&2; exit 3; }
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

_rsync_excludes=(
  --exclude='.env'
  --exclude='__pycache__/'
  --exclude='*.pyc'
  --exclude='.venv/'
  --exclude='log/'
  --exclude='build/'
  --exclude='install/'
  --exclude='.git/'
  --exclude='.DS_Store'
  # point_lio 官方示例 gif ~246M，源码联调不需要
  --exclude='point_lio_ros2/image/'
)

# pull: 远端 → 本地。带 --delete，本地严格追远端。
rsync_pull() {
  command -v rsync >/dev/null || { echo "need rsync" >&2; exit 3; }
  local sub="${1:-}"
  local remote_path="qt${sub:+/$sub}"
  local local_path="$LOCAL_QT${sub:+/$sub}"
  mkdir -p "$local_path"
  rsync -av --delete "${_rsync_excludes[@]}" \
    -e "$(_rsync_ssh_cmd)" \
    "$USER@$HOST:$remote_path/" \
    "$local_path/"
}

# push: 本地 → 远端。默认 dry-run；--yes 才真写；不带 --delete。
rsync_push() {
  command -v rsync >/dev/null || { echo "need rsync" >&2; exit 3; }
  local sub="${1:-}"
  local yes="${2:-}"
  if [[ -z "$sub" ]]; then
    echo "push 必须显式指定子目录，例：jetson.sh push car_web" >&2
    exit 2
  fi
  local local_path="$LOCAL_QT/$sub"
  local remote_path="qt/$sub"
  if [[ ! -d "$local_path" ]]; then
    echo "本地目录不存在：$local_path" >&2
    exit 2
  fi

  local mode="dry-run" flag=(-n)
  if [[ "$yes" == "--yes" ]]; then
    mode="write"
    flag=()
    echo ">>> push $local_path/ → $USER@$HOST:$remote_path/ (真写，无 --delete)"
  else
    echo ">>> push $local_path/ → $USER@$HOST:$remote_path/ (dry-run，加 --yes 才真写)"
  fi

  # 先确保远端父目录存在
  if [[ "$mode" == "write" ]]; then
    ssh_run "mkdir -p 'qt/$sub'"
  fi

  rsync -av "${flag[@]}" "${_rsync_excludes[@]}" \
    -e "$(_rsync_ssh_cmd)" \
    "$local_path/" \
    "$USER@$HOST:$remote_path/"
}

usage() {
  cat <<'USAGE'
Usage:
  jetson.sh                         interactive ssh
  jetson.sh --profile vm            interactive ssh (use HOST_VM/USER_VM/..)
  jetson.sh probe                   inspect remote host
  jetson.sh --profile vm probe      inspect remote host (vm profile)
  jetson.sh pull [subdir]           remote ~/qt/[subdir] -> local mirror/[subdir]
  jetson.sh push <subdir> [--yes]   local mirror/[subdir] -> remote ~/qt/[subdir]
  jetson.sh ros2 <command>          manage remote ~/qt/ros2_ws
  jetson.sh <remote command>        run one remote command

ROS2 commands (注意：远端原版无 scripts/ 时 start/stop/deploy 不可用):
  ros2 push                         dry-run sync mirror/ros2_ws -> ~/qt/ros2_ws
  ros2 push --yes                   sync mirror/ros2_ws -> ~/qt/ros2_ws
  ros2 build                        colcon build on Jetson（需远端有对应包）
  ros2 deploy                       push --yes + colcon build
  ros2 start|stop|restart           依赖远端 scripts/ros2_stack.sh（原版已撤回，勿当日常入口）
  ros2 status|logs [-f]
  ros2 lio-* / verify               同上，仅归档方案曾使用
USAGE
}

remote_ros2_build() {
  ssh_run "
    set -e
    cd ~/$REMOTE_ROS2_WS
    find scripts src -type f \\( -name '*.sh' -o -name '*.py' \\) -print0 2>/dev/null | xargs -0 -r sed -i 's/\\r$//'
    chmod +x scripts/*.sh 2>/dev/null || true
    set +u
    source /opt/ros/humble/setup.bash
    set -u
    colcon build --packages-select cmd_vel_car_web_bridge unitree_lidar_ros2 point_lio lio_odom_adapter
  "
}

remote_ros2_stack() {
  local cmd="${1:-status}"
  shift || true
  ssh_run "bash ~/$REMOTE_ROS2_WS/scripts/ros2_stack.sh '$cmd' $*"
}

remote_lio_build() {
  ssh_run "
    set -e
    cd ~/$REMOTE_ROS2_WS
    find scripts src -type f \\( -name '*.sh' -o -name '*.py' \\) -print0 2>/dev/null | xargs -0 -r sed -i 's/\\r$//'
    chmod +x scripts/*.sh 2>/dev/null || true
    set +u
    source /opt/ros/humble/setup.bash
    set -u
    colcon build --packages-select point_lio lio_odom_adapter
  "
}

remote_lio_stack() {
  local cmd="${1:-status}"
  shift || true
  ssh_run "bash ~/$REMOTE_ROS2_WS/scripts/lio_stack.sh '$cmd' $*"
}

ros2_cmd() {
  local cmd="${1:-help}"
  shift || true
  case "$cmd" in
    help|-h|--help)
      usage
      ;;
    push)
      rsync_push ros2_ws "${1:-}"
      ;;
    build)
      remote_ros2_build
      ;;
    deploy)
      rsync_push ros2_ws --yes
      remote_ros2_build
      ;;
    start|stop|restart|status|logs)
      remote_ros2_stack "$cmd" "$@"
      ;;
    verify)
      ssh_run "bash ~/$REMOTE_ROS2_WS/scripts/bridge_stack.sh verify $*"
      ;;
    lio-build)
      remote_lio_build
      ;;
    lio-start|lio-stop|lio-status|lio-logs)
      remote_lio_stack "${cmd#lio-}" "$@"
      ;;
    *)
      echo "unknown ros2 command: $cmd" >&2
      usage >&2
      exit 2
      ;;
  esac
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
    ssh_run '
      set +e
      echo "== host =="; hostname; uname -a; uptime
      echo "== os ==";   grep -E "^(NAME|VERSION)=" /etc/os-release
      cat /etc/nv_tegra_release 2>/dev/null | head -1
      echo "== disk =="; df -h / /home 2>/dev/null
      echo "== cuda =="; command -v nvcc && nvcc --version | tail -2
      echo "== ros ==";  ls /opt/ros 2>/dev/null
      echo "== ~/qt =="; ls -la ~/qt 2>/dev/null
    '
    ;;
  pull)
    shift
    rsync_pull "${1:-}"
    ;;
  push)
    shift
    rsync_push "${1:-}" "${2:-}"
    ;;
  ros2)
    shift
    ros2_cmd "$@"
    ;;
  *)
    ssh_run "$*"
    ;;
esac
