from glob import glob

from setuptools import find_packages, setup

package_name = "omy_hx5_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/urdf", glob("urdf/*.xacro")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
        ("share/" + package_name + "/rviz", glob("rviz/*.rviz")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="SHAPE-UP Tactile",
    maintainer_email="chlgkals0730@gmail.com",
    description="OMY F3M robot-PC bringup with a left HX5-D20 on the END tool bus.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "omy_hx5_arm_bridge = omy_hx5_bringup.arm_bridge:main",
            "omy_hx5_hand_bridge = hx5_teleop.cli:main",
            "omy_hx5_unpack_and_hold = omy_hx5_bringup.unpack:main",
            "omy_hx5_end_proxy_probe = omy_hx5_bringup.end_proxy:main",
            "omy_hx5_end_recover = omy_hx5_bringup.end_recover:main",
            "omy_hx5_end_preset = omy_hx5_bringup.end_preset:main",
            "omy_hx5_end_direct_prepare = omy_hx5_bringup.end_direct_prepare:main",
            "omy_hx5_end_torque_on = omy_hx5_bringup.end_torque_on:main",
            "omy_hx5_end_direct = omy_hx5_bringup.end_direct_node:main",
        ],
    },
)
