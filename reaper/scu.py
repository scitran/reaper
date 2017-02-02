# @author:  Reno Bowen
#           Gunnar Schaefer

"""
SCU is a module that wraps the findscu and movescu commands, which are part of DCMTK.

Usage involves the instantiation of an SCU object, which maintains knowledge of the caller and callee (data requester
and data source, respectively).

Specific Query objects are constructed (e.g., SeriesQuery, if you intend to search for or move a series) and passed to
the find() or move() methods of an SCU object.
"""

import os
import re
import shlex
import logging
import subprocess

log = logging.getLogger(__name__)

RESPONSE_RE = re.compile(
    r'I: Find Response.*\n.*\n'
    r'I: # Dicom-Data-Set\n'
    r'I: # Used TransferSyntax: (?P<txx>.+)\n'
    r'(?P<dicom_cvs>(I: \(.+\) .+\n){2,})'
)

DICOM_CV_RE = re.compile(
    r'.*\((?P<idx_0>[0-9a-f]{4}),(?P<idx_1>[0-9a-f]{4})\) '
    r'(?P<type>\w{2}) (?P<value>.+)#[ ]*(?P<length>\d+),[ ]*(?P<n_elems>\d+) (?P<label>\w+)\n'
)

QUERY_TEMPLATE = {
    'StudyInstanceUID': '',
    'StudyDate': '',
    'StudyTime': '',
    'SeriesInstanceUID': '',
    'NumberOfSeriesRelatedInstances': '',
    'PatientID': '',
}


class SCUQuery(dict):

    """SCUQuery class"""

    def __init__(self, **kwargs):
        super(SCUQuery, self).__init__(QUERY_TEMPLATE)
        self.update(**kwargs)


class SCU(object):

    """
    SCU stores information required to communicate with the scanner during calls to find() and move().

    Instantiated with the host, port, and aet of the scanner, as well as the aec of the calling machine. Incoming port
    is optional (default=port).
    """

    def __init__(self, host, port, return_port, aet, aec):
        self.host = host
        self.port = port
        self.return_port = return_port
        self.aet = aet
        self.aec = aec

    def find(self, query):
        """ Construct a findscu query. Return a list of Response objects. """
        cmd = 'findscu -v %s' % self.query_string(query)
        log.debug(cmd)
        output = ''
        try:
            output = subprocess.check_output(shlex.split(cmd), stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as ex:
            log.debug('%s: %s', type(ex).__name__, ex)
            if output:
                log.debug(output)
        if output and re.search(r'I: Received Final Find Response \(Success\)', output):
            return [Response(query.kwargs.keys(), match_obj.groupdict()) for match_obj in RESPONSE_RE.finditer(output)]
        else:
            log.warning(cmd)
            log.warning(output)
            return []

    def move(self, query, dest_path='.'):
        """Construct a movescu query. Return the count of images successfully transferred."""
        cmd = 'movescu -v -od %s --port %s %s' % (dest_path, self.return_port, self.query_string(query))
        log.debug(cmd)
        output = ''
        try:
            output = subprocess.check_output(shlex.split(cmd), stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as ex:
            log.debug('%s: %s', type(ex).__name__, ex)
            if output:
                log.debug(output)
        if output:
            success = bool(re.search(r'I: Received Final Move Response \(Success\)', output))
            img_cnt = len(os.listdir(dest_path))
            if not success:
                log.debug(output)
        else:
            success = False
            img_cnt = 0
        return success, img_cnt

    def query_string(self, query):
        """Convert a query into a string to be appended to a findscu or movescu call."""
        return '-S -aet %s -aec %s %s %s %s' % (self.aet, self.aec, query, self.host, str(self.port))


class Query(object):

    """
    Query superclass, which accepts a retrieve level (e.g., 'Study') and a series of keyword arguments (e.g.,
    StudyNumber="500").
    """

    # pylint: disable=too-few-public-methods

    def __init__(self, retrieve_level, **kwargs):
        self.retrieve_level = retrieve_level
        self.kwargs = kwargs

    def __str__(self):
        string = '-k QueryRetrieveLevel="%s"' % self.retrieve_level
        for key, value in self.kwargs.items():
            string += ' -k %s="%s"' % (str(key), str(value))
        return string

    def __repr__(self):
        return 'Query<retrieve_level=%s, kwargs=%s>' % (self.retrieve_level, self.kwargs)


class StudyQuery(Query):
    # pylint: disable=missing-docstring,too-few-public-methods
    def __init__(self, **kwargs):
        super(StudyQuery, self).__init__('STUDY', **kwargs)


class SeriesQuery(Query):
    # pylint: disable=missing-docstring,too-few-public-methods
    def __init__(self, **kwargs):
        kwargs.setdefault('StudyInstanceUID', '')
        super(SeriesQuery, self).__init__('SERIES', **kwargs)


class ImageQuery(Query):
    # pylint: disable=missing-docstring,too-few-public-methods
    def __init__(self, **kwargs):
        super(ImageQuery, self).__init__('IMAGE', **kwargs)


class DicomCV(object):

    """Detailed DicomCV object."""

    # pylint: disable=too-few-public-methods

    def __init__(self, dicom_cv_dict):
        self.idx = (dicom_cv_dict['idx_0'], dicom_cv_dict['idx_1'])
        self.value = dicom_cv_dict['value'].strip('[]= ')
        self.length = dicom_cv_dict['length']
        self.n_elems = dicom_cv_dict['n_elems']
        self.type_ = dicom_cv_dict['type']
        self.label = dicom_cv_dict['label']


class Response(dict):

    """
    Dictionary of CVs corresponding to one (of potentially many) responses generated by a findscu call. Supports tab
    completion of dictionary elements as members.
    """

    def __init__(self, requested_cv_names, response_dict):
        dict.__init__(self)
        self.transfer_syntax = response_dict['txx']
        self.dicom_cv_list = [DicomCV(match_obj.groupdict()) for match_obj in DICOM_CV_RE.finditer(response_dict['dicom_cvs'])]
        for cv_name in requested_cv_names:
            self[cv_name] = None
        for cv in self.dicom_cv_list:
            if cv.value == '(no value available)':
                self[cv.label] = ''
            else:
                self[cv.label] = cv.value.strip('\x00')

    def __dir__(self):
        """Return list of dictionary elements for tab completion in utilities like IPython."""
        return self.keys()

    def __getattr__(self, name):
        """Allow access of dictionary elements as members."""
        if name in self:
            return self[name]
        else:
            log.debug('Response: %s', self)
            raise AttributeError(name)
