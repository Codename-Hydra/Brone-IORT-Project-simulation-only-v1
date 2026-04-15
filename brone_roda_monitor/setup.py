from setuptools import setup
import os
from glob import glob

package_name = 'brone_roda_monitor'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/web', glob('web/*')),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/scripts', glob('scripts/*.sh')),
        ('share/' + package_name + '/config', glob('config/*.xml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='BRone Developer',
    maintainer_email='developer@example.com',
    description='BRone Roda Power Monitor & Telemetry Dashboard',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'roda_telemetry = brone_roda_monitor.roda_telemetry_node:main',
            'roda_dashboard = brone_roda_monitor.roda_dashboard_node:main',
            'roda_demo_publisher = brone_roda_monitor.roda_demo_publisher:main',
            'roda_motion_test = brone_roda_monitor.roda_motion_test:main',
            'roda_gamepad_teleop = brone_roda_monitor.roda_gamepad_teleop:main',
            'roda_serial_controller = brone_roda_monitor.roda_serial_controller:main',
        ],
    },
)
