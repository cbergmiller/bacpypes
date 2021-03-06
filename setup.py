#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

requirements = [
    # no external requirements
]

setup_requirements = [
    'pytest-runner',
    ]

test_requirements = [
    'pytest',
    'bacpypes',
]

setup(
    name='bacpypes',
    version='1.0.0',
    description='BACnet Communications Library',
    long_description='BACpypes provides a BACnet application layer and network layer written in Python.',
    author='Joel Bender, Christian Bergmiller',
    author_email='',
    url='https://github.com/cbergmiller/bacpypes',
    packages=find_packages(),
    package_dir={
        'bacpypes': 'bacpypes',
    },
    include_package_data=True,
    install_requires=requirements,
    license='MIT',
    zip_safe=False,
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.6',
    ],

    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
)
