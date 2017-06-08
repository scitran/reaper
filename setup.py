import os

from setuptools import setup, find_packages

install_requires = [
    'pydicom',
    'python-dateutil',
    'pytz',
    'requests<2.16',
    'requests_toolbelt',
    'tzlocal',
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
