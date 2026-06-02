from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ament_index_python.packages import PackageNotFoundError, get_package_prefix


REMOTE_WORKSPACE_MARKERS = (
    "/home/nvidia/ros2_ws",
    "/home/nvidia/slam_ws",
    "\\ros2_ws\\",
    "\\slam_ws\\",
)

DIAGNOSTIC_PACKAGES = (
    "slam_bringup",
    "slam_frontend",
    "slam_perception",
)

FULL_PACKAGES = (
    "unitree_lidar_ros2",
    "point_lio",
    "point-lio-slam",
    "sam-qn",
    "localization_qn",
    "nano_gicp",
    "quatro",
)


def _is_remote_workspace(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(marker.replace("\\", "/") in normalized for marker in REMOTE_WORKSPACE_MARKERS)


def _check_package(name: str) -> tuple[str, str, str]:
    try:
        prefix = get_package_prefix(name)
    except PackageNotFoundError:
        return name, "missing", ""
    if _is_remote_workspace(prefix):
        return name, "remote", prefix
    return name, "ok", prefix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that SLAM packages resolve from this project.")
    parser.add_argument(
        "--profile",
        choices=("diagnostic", "full"),
        default="full",
        help="diagnostic checks only project-owned Python packages; full checks vendored SLAM packages too.",
    )
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Printed for context only; package resolution comes from the sourced ROS environment.",
    )
    args = parser.parse_args(argv)

    packages = list(DIAGNOSTIC_PACKAGES)
    if args.profile == "full":
        packages.extend(FULL_PACKAGES)

    print(f"project_root={Path(args.project_root).resolve()}")
    failed = False
    for name in packages:
        pkg, status, prefix = _check_package(name)
        if status == "ok":
            print(f"OK      {pkg}: {prefix}")
        elif status == "remote":
            failed = True
            print(f"REMOTE  {pkg}: {prefix}")
        else:
            failed = True
            print(f"MISSING {pkg}")

    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
