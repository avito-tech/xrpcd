#!/usr/bin/env python2.7
# coding=utf-8


from setuptools import setup, find_packages

import xrpcd


def requirements_by_file(filenmae):
    with open(filenmae) as f:
        return [reqspec for reqspec in f.read().splitlines() if
                not reqspec.startswith('-') or not reqspec.startswith('#')]


setup(
    name=xrpcd.__name__,
    version=xrpcd.__version__,
    description='PostgreSQL RPC built on top of pgq.',
    packages=find_packages(),
    include_package_data=True,
    package_data={
        'xrpcd': ['xrpcd/conf/xrpcd.ini.dist', ]
    },
    install_requires=requirements_by_file('requirements.txt'),
    tests_require=[],
    entry_points="""
    [console_scripts]
    xrpcd=xrpcd.cli:main
    """,
    zip_safe=False,
    url='https://github.com/avito-tech/xrpcd',
    maintainer='Avito Team',
    maintainer_email='tech [at] avito [dot] ru',
)
