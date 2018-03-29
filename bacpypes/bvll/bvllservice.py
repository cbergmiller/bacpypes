#!/usr/bin/python

"""
BACnet Virtual Link Layer Service
"""

import logging
from ..comm import ApplicationServiceElement

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['BVLLServiceElement']


class BVLLServiceElement(ApplicationServiceElement):

    def __init__(self, aseID=None):
        if DEBUG: _logger.debug('__init__ aseID=%r', aseID)
        ApplicationServiceElement.__init__(self, aseID)

    def indication(self, npdu):
        if DEBUG: _logger.debug('indication %r %r', npdu)
        # redirect
        fn = npdu.__class__.__name__
        if hasattr(self, fn):
            getattr(self, fn)(npdu)
        else:
            _logger.warning('no handler for %s', fn)

    def confirmation(self, npdu):
        if DEBUG: _logger.debug('confirmation %r %r', npdu)
        # redirect
        fn = npdu.__class__.__name__
        if hasattr(self, fn):
            getattr(self, fn)(npdu)
        else:
            _logger.warning('no handler for %s', fn)
