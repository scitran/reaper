from setuptools import setup, find_packages
import os

version = '0.1'

tests_require = []

setup(
    name='scitran.reaper',
    version=version,
    description='Data collection service',
    classifiers=[
        'Programming Language :: Python',
    ],
    keywords='scitran',
    author='Gunnar Schaefer',
    author_email='gsfr@stanford.edu',
    url='http://scitran.github.io/',
    packages=find_packages(),
    namespace_packages=['scitran'],
    install_requires=[
        'pytz',
        'tzlocal',
        'requests',
        'pydicom',
        'numpy',
        'nibabel',
        'dcmstack',
        'scitran.data',
    ],
    entry_points={
        'console_scripts': [
            'dicom_net_reaper=scitran.reaper.dicom_net_reaper:main',
            'dicom_file_reaper=scitran.reaper.dicom_file_reaper:main',
            'pfile_reaper=scitran.reaper.pfile_reaper:main',
        ],
    },
    tests_require=tests_require,
)
