from setuptools import setup

setup(
    name="elastic-3am-killer-test-common",
    version="0.1.0",
    packages=["common"],
    package_dir={"common": "."},
    install_requires=[
        "httpx",
        "a2a",
    ],
)
