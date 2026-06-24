# Development-only stack scripts

Not daily entrypoints. Use the two production stacks instead:

```bash
~/ros_ws/scripts/android_stack.sh start   # Android full stack
~/ros_ws/scripts/qt_stack.sh start        # Qt full stack
```

| Script | Purpose |
|--------|---------|
| `dev/camera_stack.sh` | Camera + web_video_server only (no bringup/json) |
| `dev/json_stack.sh` | Foreground or background bringup + JSON bridge debugging |

These live under `scripts/dev/` only; there is no parent-directory stub.
