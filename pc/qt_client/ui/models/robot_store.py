from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from .robot_info import RobotInfo, default_robot


def default_store_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "robots.json"


class RobotStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            path = default_store_path()
        self._path = path
        self._robots: List[RobotInfo] = []
        self.load()

    @property
    def path(self) -> Path:
        return self._path

    def robots(self) -> List[RobotInfo]:
        return list(self._robots)

    def get(self, robot_id: str) -> Optional[RobotInfo]:
        for robot in self._robots:
            if robot.id == robot_id:
                return robot
        return None

    def add(self, robot: RobotInfo) -> None:
        self._robots.append(robot)
        self.save()

    def update(self, robot: RobotInfo) -> bool:
        for index, existing in enumerate(self._robots):
            if existing.id == robot.id:
                self._robots[index] = robot
                self.save()
                return True
        return False

    def remove(self, robot_id: str) -> bool:
        for index, robot in enumerate(self._robots):
            if robot.id == robot_id:
                self._robots.pop(index)
                self.save()
                return True
        return False

    def load(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"WARN: robot config directory unavailable: {exc}")
            self._robots = [default_robot()]
            return
        if not self._path.is_file():
            self._robots = [default_robot()]
            self.save()
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._robots = [default_robot()]
            self.save()
            return
        if not isinstance(raw, list):
            self._robots = [default_robot()]
            self.save()
            return
        robots: List[RobotInfo] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                robots.append(RobotInfo.from_dict(item))
            except (TypeError, ValueError):
                continue
        if not robots:
            self._robots = [default_robot()]
            self.save()
            return
        self._robots = robots

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"WARN: robot config directory unavailable: {exc}")
            return
        payload = [robot.to_dict() for robot in self._robots]
        try:
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"WARN: robot config save failed: {exc}")
