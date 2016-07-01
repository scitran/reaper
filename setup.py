import os

from setuptools import setup, find_packages

install_requires = [
    'pydicom',
    'python-dateutil',
    'pytz',
    'requests',
    'requests_toolbelt',
    'tzlocal',
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
    scripts = [os.path.join('bin', fn) for fn in os.listdir('bin') if not fn.startswith('.')],
    package_data = {'': ['*.json']},
    install_requires =  install_requires,
)
