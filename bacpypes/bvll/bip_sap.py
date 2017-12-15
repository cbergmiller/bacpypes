
import logging
from ..comm import ServiceAccessPoint

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['BIPSAP']


class BIPSAP(ServiceAccessPoint):

    def __init__(self, sap=None):
        """A BIP service access point."""
        if DEBUG: _logger.debug("__init__ sap=%r", sap)
        ServiceAccessPoint.__init__(self, sap)

    def sap_indication(self, pdu):
        if DEBUG: _logger.debug("sap_indication %r", pdu)
        # this is a request initiated by the ASE, send this downstream
        self.request(pdu)

    def sap_confirmation(self, pdu):
        if DEBUG: _logger.debug("sap_confirmation %r", pdu)
        # this is a response from the ASE, send this downstream
        self.request(pdu)