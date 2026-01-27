from setuptools import find_packages, setup

setup(
    name="elastic-3am-killer-test-common",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "httpx",
        "a2a",
    ],
)
