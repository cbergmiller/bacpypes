#!/usr/bin/python

"""
Application Layer
"""

import logging
from ..comm import ServiceAccessPoint, ApplicationServiceElement
from ..apdu import AbortPDU, ComplexAckPDU, ConfirmedRequestPDU, Error, ErrorPDU, RejectPDU, SimpleAckPDU, \
    UnconfirmedRequestPDU, unconfirmed_request_types, confirmed_request_types, complex_ack_types, error_types
from ..errors import RejectException, AbortException

_logger = logging.getLogger(__name__)
__all__ = ['ApplicationServiceAccessPoint']


class ApplicationServiceAccessPoint(ApplicationServiceElement, ServiceAccessPoint):
    """
    ApplicationServiceAccessPoint
    """

    def __init__(self, aseID=None, sapID=None):
        ApplicationServiceElement.__init__(self, aseID)
        ServiceAccessPoint.__init__(self, sapID)

    def indication(self, apdu):
        if isinstance(apdu, ConfirmedRequestPDU):
            atype = confirmed_request_types.get(apdu.apduService)
            if not atype:
                # no confirmed request decoder
                return
            # assume no errors found
            error_found = None
            try:
                xpdu = atype()
                xpdu.decode(apdu)
            except (RejectException, AbortException) as err:
                error_found = err
            else:
                # no error so far, keep going
                try:
                    # forward the decoded packet
                    self.sap_request(xpdu)
                except (RejectException, AbortException) as err:
                    error_found = err
            # if there was an error, send it back to the client
            if isinstance(error_found, RejectException):
                # reject exception
                reject_pdu = RejectPDU(reason=error_found.rejectReason)
                reject_pdu.set_context(apdu)
                # send it to the client
                self.response(reject_pdu)
            elif isinstance(error_found, AbortException):
                # abort exception
                abort_pdu = AbortPDU(reason=error_found.abortReason)
                abort_pdu.set_context(apdu)
                # send it to the client
                self.response(abort_pdu)
        elif isinstance(apdu, UnconfirmedRequestPDU):
            atype = unconfirmed_request_types.get(apdu.apduService)
            if not atype:
                # no unconfirmed request decoder
                return
            try:
                xpdu = atype()
                xpdu.decode(apdu)
            except (RejectException, AbortException):
                return
            try:
                # forward the decoded packet
                self.sap_request(xpdu)
            except (RejectException, AbortException):
                pass
        else:
            # unknown PDU type?!
            pass

    def sap_indication(self, apdu):
        if isinstance(apdu, ConfirmedRequestPDU):
            try:
                xpdu = ConfirmedRequestPDU()
                apdu.encode(xpdu)
                apdu._xpdu = xpdu
            except Exception as err:
                _logger.exception(f'confirmed request encoding error: {err!r}')
                return
        elif isinstance(apdu, UnconfirmedRequestPDU):
            try:
                xpdu = UnconfirmedRequestPDU()
                apdu.encode(xpdu)
                apdu._xpdu = xpdu
            except Exception as err:
                _logger.exception(f'unconfirmed request encoding error: {err!r}')
                return
        else:
            # unknown PDU type?!
            return
        # forward the encoded packet
        self.request(xpdu)
        # if the upper layers of the application did not assign an invoke ID,
        # copy the one that was assigned on its way down the stack
        if isinstance(apdu, ConfirmedRequestPDU) and apdu.apduInvokeID is None:
            # pass invoke ID upstream
            apdu.apduInvokeID = xpdu.apduInvokeID

    def confirmation(self, apdu):
        if isinstance(apdu, SimpleAckPDU):
            xpdu = apdu
        elif isinstance(apdu, ComplexAckPDU):
            atype = complex_ack_types.get(apdu.apduService)
            if not atype:
                # no complex ack decoder
                return
            try:
                xpdu = atype()
                xpdu.decode(apdu)
            except Exception:
                # unconfirmed request decoding error
                return
        elif isinstance(apdu, ErrorPDU):
            atype = error_types.get(apdu.apduService)
            if not atype:
                # no special error decoder
                atype = Error
            try:
                xpdu = atype()
                xpdu.decode(apdu)
            except Exception as err:
                _logger.exception(f'error PDU decoding error: {err!r}')
                xpdu = Error(errorClass=0, errorCode=0)
        elif isinstance(apdu, RejectPDU):
            xpdu = apdu
        elif isinstance(apdu, AbortPDU):
            xpdu = apdu
        else:
            # unknown PDU type
            return
        # forward the decoded packet
        self.sap_response(xpdu)

    def sap_confirmation(self, apdu):
        if isinstance(apdu, SimpleAckPDU):
            xpdu = apdu
        elif isinstance(apdu, ComplexAckPDU):
            xpdu = ComplexAckPDU()
            apdu.encode(xpdu)
        elif isinstance(apdu, ErrorPDU):
            xpdu = ErrorPDU()
            apdu.encode(xpdu)
        elif isinstance(apdu, RejectPDU):
            xpdu = apdu
        elif isinstance(apdu, AbortPDU):
            xpdu = apdu
        else:
            # unknown PDU type
            return
        # forward the encoded packet
        self.response(xpdu)
