from setuptools import setup, find_packages
import os

version = '0.1'

tests_require = []

setup(name='scitran.reaper',
      version=version,
      description='Data collection service',
      classifiers=[
        "Programming Language :: Python",
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
        'numpy',
        'pydicom==0.9.9',
        'nibabel',
        'dcmstack',
        'scitran.data',
        ],
      dependency_links=[
        'https://github.com/scitran/pydicom/archive/v0.9.9.zip#egg=pydicom-0.9.9',
        'https://github.com/moloney/dcmstack/archive/master.zip#egg=dcmstack-0.7.0',
        'https://github.com/scitran/data/archive/master.zip#egg=scitran.data-1.0'
        ],
      entry_points = {
          'console_scripts':
            ['dicom_net_reaper = scitran.reaper.dicom_reaper:main',
            'dicom_file_reaper = scitran.reaper.dicom_file_reaper:main',
            'pfile_reaper = scitran.reaper.pfile_reaper:main',
            ]},
      tests_require=tests_require,
      )
