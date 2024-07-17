from setuptools import setup, find_packages

setup(
    name='generate_data',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        'bs4',
        'geopy',
        'diskcache'
    ],
    entry_points={
        'console_scripts': [
            'generate_data = generate_data.main:main',
        ],
    },
)
