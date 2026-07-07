from setuptools import find_packages, setup

package_name = "cmd_vel_car_web_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages",
            ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="ros-dev",
    maintainer_email="dev@localhost",
    description=(
        "Dry-run bridge from /cmd_vel Twist to discrete action string. "
        "Does NOT call car_web in this stage."
    ),
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "bridge = cmd_vel_car_web_bridge.node:main",
        ],
    },
)
