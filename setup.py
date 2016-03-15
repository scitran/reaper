import os

from setuptools import setup, find_packages

install_requires = [
    'python-dateutil',
    'pytz',
    'tzlocal',
    'requests_toolbelt',
    'pydicom',
]

setup(
    name = 'reaper',
    version = 'bali.2.0',
    description = 'SciTran Instrument Integration',
    author = 'Gunnar Schaefer',
    author_email = 'gsfr@stanford.edu',
    url = 'https://github.com/scitran/reaper',
    license = 'MIT',
    packages = find_packages(),
    scripts = [os.path.join('bin', fn) for fn in os.listdir('bin')],
    package_data = {'': ['*.json']},
    install_requires =  install_requires,
)
