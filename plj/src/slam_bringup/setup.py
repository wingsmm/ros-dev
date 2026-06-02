from glob import glob
from setuptools import setup

package_name = "slam_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/urdf", glob("urdf/*.urdf")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="nvidia",
    maintainer_email="nvidia@example.com",
    description="Launch and configuration package for the L1 SLAM stair-climbing system.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "backend_watchdog = slam_bringup.backend_watchdog_node:main",
            "workspace_doctor = slam_bringup.workspace_doctor:main",
        ],
    },
)
