#!/usr/bin/python

import socket
import struct
import logging

try:
    import netifaces
except ImportError:
    netifaces = None

from ..debugging import ModuleLogger, bacpypes_debugging, btox, xtob
from ..comm import PDUData
from .pci import PCI

# pack/unpack constants
_short_mask = 0xFFFF
_long_mask = 0xFFFFFFFF

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['PDU']


class PDU(PCI, PDUData):
    """
    Link Layer PDU
    """
    def __init__(self, *args, **kwargs):
        if DEBUG: _logger.debug('PDU.__init__ %r %r', args, kwargs)
        super(PDU, self).__init__(*args, **kwargs)

    def __str__(self):
        return f'<{self.__class__.__name__} {self.pduSource} -> {self.pduDestination} : {btox(self.pduData, ".")}>'

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if DEBUG: _logger.debug('dict_contents use_dict=%r as_class=%r', use_dict, as_class)
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # call into the two base classes
        self.pci_contents(use_dict=use_dict, as_class=as_class)
        self.pdudata_contents(use_dict=use_dict, as_class=as_class)
        # return what we built/updated
        return use_dict
