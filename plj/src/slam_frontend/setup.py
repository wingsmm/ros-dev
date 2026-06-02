from glob import glob
from setuptools import setup

package_name = "slam_frontend"

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
    description="Self-contained lightweight LiDAR odometry frontend for project validation.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "simple_lidar_frontend = slam_frontend.simple_lidar_frontend_node:main",
        ],
    },
)
