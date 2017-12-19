
import logging
from ..debugging import btox
from .pci import PCI
from .pdu_data import PDUData

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['PDU']


class PDU(PCI, PDUData):
    """
    A Protocol Data Unit (PDU) is the name for a collection of information that
    is passed between two entities.  It is composed of Protcol Control Information
    (PCI) - information about addressing, processing instructions - and data.
    The set of classes in this module are not specific to BACnet.
    """
    def __init__(self, data=None, **kwargs):
        if DEBUG: _logger.debug('__init__ %r %r', data, kwargs)
        # pick up some optional kwargs
        user_data = kwargs.get('user_data', None)
        source = kwargs.get('source', None)
        destination = kwargs.get('destination', None)
        # carry source and destination from another PDU
        # so this can act like a copy constructor
        if isinstance(data, PDU):
            # allow parameters to override values
            user_data = user_data or data.pduUserData
            source = source or data.pduSource
            destination = destination or data.pduDestination
        # now continue on
        PCI.__init__(self, user_data=user_data, source=source, destination=destination)
        PDUData.__init__(self, data)

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
