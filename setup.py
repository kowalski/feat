#!/usr/bin/env python

import os
from setuptools import setup, find_packages

setup(name='feat',
      version='0.1.2',
      description='Flumotion Asynchronous Autonomous Agent Toolkit',
      author='Flumotion Developers',
      author_email='coreteam@flumotion.com',
      platforms=['any'],
      package_dir={'': 'src',
                   'paisley': 'src/feat/extern/paisley/paisley/'},
      packages=find_packages(where='src') + find_packages('src/feat/extern/paisley'),
      scripts=['bin/feat',
               'src/feat/bin/host.py',
               'src/feat/bin/feat-couchpy',
               'src/feat/bin/standalone.py'],
      package_data={'': ['src/feat/agencies/net/amqp0-8.xm']},
)
