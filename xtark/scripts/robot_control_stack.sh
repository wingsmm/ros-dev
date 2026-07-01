#!/usr/bin/env bash
set -euo pipefail
# Deprecated: use qt_stack.sh radar2d-*
ROOT="$(cd "$(dirname "$0")" && pwd)"
cmd="${1:-help}"
echo "[deprecated] robot_control_stack.sh -> qt_stack.sh radar2d-*" >&2
case "$cmd" in
  start) shift; exec "$ROOT/qt_stack.sh" radar2d-start "$@" ;;
  stop) shift; exec "$ROOT/qt_stack.sh" radar2d-stop "$@" ;;
  restart) shift; exec "$ROOT/qt_stack.sh" radar2d-restart "$@" ;;
  status) shift; exec "$ROOT/qt_stack.sh" radar2d-status "$@" ;;
  check) shift; exec "$ROOT/qt_stack.sh" radar2d-check "$@" ;;
  *) exec "$ROOT/qt_stack.sh" "$@" ;;
esac
