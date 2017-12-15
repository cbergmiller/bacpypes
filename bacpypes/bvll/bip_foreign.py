
import logging
from ..debugging import DebugContents
from ..task import call_later
from ..comm import Client, Server
from ..link import Address, LocalBroadcast, PDU
from .bvlpdu import DistributeBroadcastToNetwork, ForwardedNPDU, OriginalUnicastNPDU, ReadBroadcastDistributionTableAck, ReadForeignDeviceTableAck, RegisterForeignDevice, Result
from .bip_sap import BIPSAP

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['BIPForeign']


class BIPForeign(BIPSAP, Client, Server, DebugContents):

    _debug_contents = ('registrationStatus', 'bbmdAddress', 'bbmdTimeToLive')

    def __init__(self, addr=None, ttl=None, sapID=None, cid=None, sid=None):
        """A BIP node."""
        if DEBUG: _logger.debug("__init__ addr=%r ttl=%r sapID=%r cid=%r sid=%r", addr, ttl, sapID, cid, sid)
        BIPSAP.__init__(self, sapID)
        Client.__init__(self, cid)
        Server.__init__(self, sid)
        # -2=unregistered, -1=not attempted or no ack, 0=OK, >0 error
        self.registrationStatus = -1
        # clear the BBMD address and time-to-live
        self.bbmdAddress = None
        self.bbmdTimeToLive = None
        # registration provided
        if addr:
            # a little error checking
            if ttl is None:
                raise RuntimeError("BBMD address and time-to-live must both be specified")
            self.register(addr, ttl)

    def indication(self, pdu):
        if DEBUG: _logger.debug("indication %r", pdu)
        # check the BBMD registration status, we may not be registered
        if self.registrationStatus != 0:
            if DEBUG: _logger.debug("    - packet dropped, unregistered")
            return
        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # make an original unicast PDU
            xpdu = OriginalUnicastNPDU(pdu, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduDestination
            # send it downstream
            self.request(xpdu)
        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # make an original broadcast PDU
            xpdu = DistributeBroadcastToNetwork(pdu, user_data=pdu.pduUserData)
            xpdu.pduDestination = self.bbmdAddress
            # send it downstream
            self.request(xpdu)
        else:
            _logger.warning("invalid destination address: %r", pdu.pduDestination)

    def confirmation(self, pdu):
        if DEBUG: _logger.debug("confirmation %r", pdu)
        # check for a registration request result
        if isinstance(pdu, Result):
            # if we are unbinding, do nothing
            if self.registrationStatus == -2:
                return
            ### make sure we have a bind request in process
            # make sure the result is from the bbmd
            if pdu.pduSource != self.bbmdAddress:
                if DEBUG: _logger.debug("    - packet dropped, not from the BBMD")
                return
            # save the result code as the status
            self.registrationStatus = pdu.bvlciResultCode
            # check for success
            if pdu.bvlciResultCode == 0:
                # schedule for a refresh
                call_later(self.bbmdTimeToLive, self.process_task)
            return
        # check the BBMD registration status, we may not be registered
        if self.registrationStatus != 0:
            if DEBUG: _logger.debug("    - packet dropped, unregistered")
            return
        if isinstance(pdu, ReadBroadcastDistributionTableAck):
            # send this to the service access point
            self.sap_response(pdu)
        elif isinstance(pdu, ReadForeignDeviceTableAck):
            # send this to the service access point
            self.sap_response(pdu)
        elif isinstance(pdu, OriginalUnicastNPDU):
            # build a vanilla PDU
            xpdu = PDU(pdu.pduData, source=pdu.pduSource, destination=pdu.pduDestination, user_data=pdu.pduUserData)
            # send it upstream
            self.response(xpdu)
        elif isinstance(pdu, ForwardedNPDU):
            # build a PDU with the source from the real source
            xpdu = PDU(pdu.pduData, source=pdu.bvlciAddress, destination=LocalBroadcast(), user_data=pdu.pduUserData)
            # send it upstream
            self.response(xpdu)
        else:
            _logger.warning("invalid pdu type: %s", type(pdu))

    def register(self, addr, ttl):
        """Initiate the process of registering with a BBMD."""
        # a little error checking
        if ttl <= 0:
            raise ValueError("time-to-live must be greater than zero")
        # save the BBMD address and time-to-live
        if isinstance(addr, Address):
            self.bbmdAddress = addr
        else:
            self.bbmdAddress = Address(addr)
        self.bbmdTimeToLive = ttl
        # install this task to run when it gets a chance
        self.process_task()

    def unregister(self):
        """Drop the registration with a BBMD."""
        pdu = RegisterForeignDevice(0)
        pdu.pduDestination = self.bbmdAddress
        # send it downstream
        self.request(pdu)
        # change the status to unregistered
        self.registrationStatus = -2
        # clear the BBMD address and time-to-live
        self.bbmdAddress = None
        self.bbmdTimeToLive = None

    def process_task(self):
        """Called when the registration request should be sent to the BBMD."""
        pdu = RegisterForeignDevice(self.bbmdTimeToLive)
        pdu.pduDestination = self.bbmdAddress
        # send it downstream
        self.request(pdu)
