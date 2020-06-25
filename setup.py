from setuptools import setup, find_packages
from hdhr_disk_space_monitor import __about__

setup(
  name=__about__.__name__,
  version=__about__.__version__,
  description=(__about__.__description__),
  long_description='README.md',
  long_description_content_type='text/markdown',
  url=__about__.__url__,
  author=__about__.__author__,
  author_email=__about__.__email__,
  license=__about__.__license__,
  packages=find_packages(),
  entry_points={'console_scripts': ['hdhr_disk_space_monitor=hdhr_disk_space_monitor.core:main']},
  classifiers=[
    'Programming Language :: Python :: 3',
    'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
    'Operating System :: OS Independent',
    ],
  platforms=['any'],
  install_requires=[
    'requests',
    ],
  data_files=[('share/hdhr_disk_space_monitor', ['hdhr_disk_space_monitor.conf.example', 'hdhr-disk-space-monitor.service' ])]
  )
