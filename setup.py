import os

from setuptools import setup, find_packages

install_requires = [
    'pydicom==0.9.9',
    'python-dateutil==2.6.0',
    'pytz==2017.2',
    'requests<2.17',
    'requests_toolbelt==0.8.0',
    'tzlocal==1.4',
]

setup(
    name = 'reaper',
    version = '2.0.0',
    description = 'SciTran Instrument Integration',
    author = 'Gunnar Schaefer',
    author_email = 'gsfr@flywheel.io',
    url = 'https://github.com/scitran/reaper',
    license = 'MIT',
    packages = find_packages(),
    scripts = [os.path.join('bin', fn) for fn in os.listdir('bin') if not fn.startswith('.')],
    install_requires =  install_requires,
)
