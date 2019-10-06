#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name="qmock",
    version="1.0.0",
    author="Alex Jacobs",
    package_dir={"": "src"},
    packages=find_packages("src"),
    install_requires=[
        "mock~=1.0; python_version<'3.3'"
    ]
)

