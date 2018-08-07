import logging
from ..comm import Client, Server
from ..link import Address, LocalBroadcast, PDU
from .bvlpdu import ForwardedNPDU, OriginalBroadcastNPDU, OriginalUnicastNPDU, ReadBroadcastDistributionTableAck, \
    ReadForeignDeviceTableAck, Result, WriteBroadcastDistributionTable, ReadBroadcastDistributionTable, \
    RegisterForeignDevice, ReadForeignDeviceTable, DeleteForeignDeviceTableEntry, DistributeBroadcastToNetwork
from .bip_sap import BIPSAP

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['BIPSimple']


class BIPSimple(BIPSAP, Client, Server):

    def __init__(self, sapID=None, cid=None, sid=None):
        """A BIP node."""
        if DEBUG: _logger.debug('__init__ sapID=%r cid=%r sid=%r', sapID, cid, sid)
        BIPSAP.__init__(self, sapID)
        Client.__init__(self, cid)
        Server.__init__(self, sid)

    def indication(self, pdu):
        if DEBUG: _logger.debug('indication %r', pdu)
        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # make an original unicast PDU
            xpdu = OriginalUnicastNPDU(pdu, destination=pdu.pduDestination, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug('    - xpdu: %r', xpdu)
            # send it downstream
            self.request(xpdu)
        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # make an original broadcast PDU
            xpdu = OriginalBroadcastNPDU(pdu, destination=pdu.pduDestination, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug('    - xpdu: %r', xpdu)
            # send it downstream
            self.request(xpdu)
        else:
            _logger.warning('invalid destination address: %r', pdu.pduDestination)

    def confirmation(self, pdu):
        if DEBUG: _logger.debug('confirmation %r', pdu)
        # some kind of response to a request
        if isinstance(pdu, Result):
            # send this to the service access point
            self.sap_response(pdu)
        elif isinstance(pdu, ReadBroadcastDistributionTableAck):
            # send this to the service access point
            self.sap_response(pdu)
        elif isinstance(pdu, ReadForeignDeviceTableAck):
            # send this to the service access point
            self.sap_response(pdu)
        elif isinstance(pdu, OriginalUnicastNPDU):
            # build a vanilla PDU
            xpdu = PDU(pdu.pduData, source=pdu.pduSource, destination=pdu.pduDestination, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug('    - xpdu: %r', xpdu)
            # send it upstream
            self.response(xpdu)
        elif isinstance(pdu, OriginalBroadcastNPDU):
            # build a PDU with a local broadcast address
            xpdu = PDU(pdu.pduData, source=pdu.pduSource, destination=LocalBroadcast(), user_data=pdu.pduUserData)
            if DEBUG: _logger.debug('    - xpdu: %r', xpdu)
            # send it upstream
            self.response(xpdu)
        elif isinstance(pdu, ForwardedNPDU):
            # build a PDU with the source from the real source
            xpdu = PDU(pdu.pduData, source=pdu.bvlciAddress, destination=LocalBroadcast(), user_data=pdu.pduUserData)
            if DEBUG: _logger.debug('    - xpdu: %r', xpdu)
            # send it upstream
            self.response(xpdu)
        elif isinstance(pdu, WriteBroadcastDistributionTable):
            # build a response
            xpdu = Result(code=0x0010, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduSource
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, ReadBroadcastDistributionTable):
            # build a response
            xpdu = Result(code=0x0020, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduSource
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, RegisterForeignDevice):
            # build a response
            xpdu = Result(code=0x0030, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduSource
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, ReadForeignDeviceTable):
            # build a response
            xpdu = Result(code=0x0040, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduSource
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, DeleteForeignDeviceTableEntry):
            # build a response
            xpdu = Result(code=0x0050, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduSource
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, DistributeBroadcastToNetwork):
            # build a response
            xpdu = Result(code=0x0060, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduSource
            # send it downstream
            self.request(xpdu)
        else:
            _logger.warning('invalid pdu type: %s', type(pdu))
