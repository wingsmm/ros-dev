from glob import glob
from setuptools import setup

package_name = "slam_perception"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools", "numpy"],
    zip_safe=True,
    maintainer="nvidia",
    maintainer_email="nvidia@example.com",
    description="Perception nodes for L1 LiDAR stair detection and climb triggering.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "stair_detector = slam_perception.stair_detector_node:main",
            "climb_supervisor = slam_perception.climb_supervisor_node:main",
        ],
    },
)
