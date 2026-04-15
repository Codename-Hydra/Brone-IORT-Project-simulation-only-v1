import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'op3_power_monitor'

setup(
    name=package_name,
    version='1.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Web dashboard static files
        ('share/' + package_name + '/web', glob('web/*')),
        # Scripts
        ('share/' + package_name + '/scripts', glob('scripts/*.sh')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OP3 Developer',
    maintainer_email='user@localhost',
    description='Power monitor node for ROBOTIS OP3 (voltage & current tracking)',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'power_monitor_node = op3_power_monitor.power_monitor_node:main',
            'power_dashboard = op3_power_monitor.power_dashboard_node:main',
            'unified_dashboard = op3_power_monitor.unified_dashboard_node:main',
            'demo_publisher = op3_power_monitor.demo_publisher:main',
        ],
    },
)

