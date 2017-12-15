import logging
from ..debugging import DebugContents
from ..task import RecurringTask
from ..comm import Client, Server
from ..link import Address, LocalBroadcast, LocalStation, PDU
from .bvlpdu import DeleteForeignDeviceTableEntry, DistributeBroadcastToNetwork, FDTEntry, ForwardedNPDU, \
    OriginalBroadcastNPDU, OriginalUnicastNPDU, ReadBroadcastDistributionTable, ReadBroadcastDistributionTableAck, \
    ReadForeignDeviceTable, ReadForeignDeviceTableAck, RegisterForeignDevice, Result, WriteBroadcastDistributionTable
from .bip_sap import BIPSAP

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['BIPBBMD']


class BIPBBMD(BIPSAP, Client, Server, DebugContents):
    """
    A BBMD node.
    """
    _debug_contents = ('bbmdAddress', 'bbmdBDT+', 'bbmdFDT+')

    def __init__(self, addr, sapID=None, cid=None, sid=None):
        if DEBUG: _logger.debug("__init__ %r sapID=%r cid=%r sid=%r", addr, sapID, cid, sid)
        BIPSAP.__init__(self, sapID)
        Client.__init__(self, cid)
        Server.__init__(self, sid)
        self.bbmdAddress = addr
        self.bbmdBDT = []
        self.bbmdFDT = []
        self.recurring_task = RecurringTask(interval=1000.0, func=self.process_task)
        self.recurring_task.start()

    def indication(self, pdu):
        if DEBUG: _logger.debug("indication %r", pdu)
        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # make an original unicast PDU
            xpdu = OriginalUnicastNPDU(pdu, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduDestination
            if DEBUG: _logger.debug("    - xpdu: %r", xpdu)
            # send it downstream
            self.request(xpdu)
        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # make an original broadcast PDU
            xpdu = OriginalBroadcastNPDU(pdu, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduDestination
            if DEBUG: _logger.debug("    - original broadcast xpdu: %r", xpdu)
            # send it downstream
            self.request(xpdu)
            # make a forwarded PDU
            xpdu = ForwardedNPDU(self.bbmdAddress, pdu, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - forwarded xpdu: %r", xpdu)
            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte != self.bbmdAddress:
                    xpdu.pduDestination = Address(((bdte.addrIP | ~bdte.addrMask), bdte.addrPort))
                    _logger.debug("        - sending to peer: %r", xpdu.pduDestination)
                    self.request(xpdu)
            # send it to the registered foreign devices
            for fdte in self.bbmdFDT:
                xpdu.pduDestination = fdte.fdAddress
                if DEBUG: _logger.debug("        - sending to foreign device: %r", xpdu.pduDestination)
                self.request(xpdu)
        else:
            _logger.warning("invalid destination address: %r", pdu.pduDestination)

    def confirmation(self, pdu):
        if DEBUG: _logger.debug("confirmation %r", pdu)
        # some kind of response to a request
        if isinstance(pdu, Result):
            # send this to the service access point
            self.sap_response(pdu)
        elif isinstance(pdu, WriteBroadcastDistributionTable):
            # build a response
            xpdu = Result(code=99, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduSource
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, ReadBroadcastDistributionTable):
            # build a response
            xpdu = ReadBroadcastDistributionTableAck(self.bbmdBDT, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduSource
            if DEBUG: _logger.debug("    - xpdu: %r", xpdu)
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, ReadBroadcastDistributionTableAck):
            # send this to the service access point
            self.sap_response(pdu)
        elif isinstance(pdu, ForwardedNPDU):
            # build a PDU with the source from the real source
            xpdu = PDU(pdu.pduData, source=pdu.bvlciAddress, destination=LocalBroadcast(), user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - upstream xpdu: %r", xpdu)
            # send it upstream
            self.response(xpdu)
            # build a forwarded NPDU to send out
            xpdu = ForwardedNPDU(pdu.bvlciAddress, pdu, destination=None, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - forwarded xpdu: %r", xpdu)
            # look for self as first entry in the BDT
            if self.bbmdBDT and (self.bbmdBDT[0] == self.bbmdAddress):
                xpdu.pduDestination = LocalBroadcast()
                if DEBUG: _logger.debug("        - local broadcast")
                self.request(xpdu)
            # send it to the registered foreign devices
            for fdte in self.bbmdFDT:
                xpdu.pduDestination = fdte.fdAddress
                if DEBUG: _logger.debug("        - sending to foreign device: %r", xpdu.pduDestination)
                self.request(xpdu)
        elif isinstance(pdu, RegisterForeignDevice):
            # process the request
            stat = self.register_foreign_device(pdu.pduSource, pdu.bvlciTimeToLive)
            # build a response
            xpdu = Result(code=stat, destination=pdu.pduSource, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - xpdu: %r", xpdu)
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, ReadForeignDeviceTable):
            # build a response
            xpdu = ReadForeignDeviceTableAck(self.bbmdFDT, destination=pdu.pduSource, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - xpdu: %r", xpdu)
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, ReadForeignDeviceTableAck):
            # send this to the service access point
            self.sap_response(pdu)
        elif isinstance(pdu, DeleteForeignDeviceTableEntry):
            # process the request
            stat = self.delete_foreign_device_table_entry(pdu.bvlciAddress)
            # build a response
            xpdu = Result(code=stat, user_data=pdu.pduUserData)
            xpdu.pduDestination = pdu.pduSource
            if DEBUG: _logger.debug("    - xpdu: %r", xpdu)
            # send it downstream
            self.request(xpdu)
        elif isinstance(pdu, DistributeBroadcastToNetwork):
            # build a PDU with a local broadcast address
            xpdu = PDU(pdu.pduData, source=pdu.pduSource, destination=LocalBroadcast(), user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - upstream xpdu: %r", xpdu)
            # send it upstream
            self.response(xpdu)
            # build a forwarded NPDU to send out
            xpdu = ForwardedNPDU(pdu.pduSource, pdu, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - forwarded xpdu: %r", xpdu)
            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte == self.bbmdAddress:
                    xpdu.pduDestination = LocalBroadcast()
                    if DEBUG: _logger.debug("        - local broadcast")
                    self.request(xpdu)
                else:
                    xpdu.pduDestination = Address(((bdte.addrIP | ~bdte.addrMask), bdte.addrPort))
                    if DEBUG: _logger.debug("        - sending to peer: %r", xpdu.pduDestination)
                    self.request(xpdu)
            # send it to the other registered foreign devices
            for fdte in self.bbmdFDT:
                if fdte.fdAddress != pdu.pduSource:
                    xpdu.pduDestination = fdte.fdAddress
                    if DEBUG: _logger.debug("        - sending to foreign device: %r", xpdu.pduDestination)
                    self.request(xpdu)
        elif isinstance(pdu, OriginalUnicastNPDU):
            # build a vanilla PDU
            xpdu = PDU(pdu.pduData, source=pdu.pduSource, destination=pdu.pduDestination, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - upstream xpdu: %r", xpdu)
            # send it upstream
            self.response(xpdu)
        elif isinstance(pdu, OriginalBroadcastNPDU):
            # build a PDU with a local broadcast address
            xpdu = PDU(pdu.pduData, source=pdu.pduSource, destination=LocalBroadcast(), user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - upstream xpdu: %r", xpdu)
            # send it upstream
            self.response(xpdu)
            # make a forwarded PDU
            xpdu = ForwardedNPDU(pdu.pduSource, pdu, user_data=pdu.pduUserData)
            if DEBUG: _logger.debug("    - forwarded xpdu: %r", xpdu)
            # send it to the peers
            for bdte in self.bbmdBDT:
                if bdte != self.bbmdAddress:
                    xpdu.pduDestination = Address(((bdte.addrIP | ~bdte.addrMask), bdte.addrPort))
                    if DEBUG: _logger.debug("        - sending to peer: %r", xpdu.pduDestination)
                    self.request(xpdu)
            # send it to the registered foreign devices
            for fdte in self.bbmdFDT:
                xpdu.pduDestination = fdte.fdAddress
                if DEBUG: _logger.debug("        - sending to foreign device: %r", xpdu.pduDestination)
                self.request(xpdu)
        else:
            _logger.warning("invalid pdu type: %s", type(pdu))

    def register_foreign_device(self, addr, ttl):
        """Add a foreign device to the FDT."""
        if DEBUG: _logger.debug("register_foreign_device %r %r", addr, ttl)
        # see if it is an address or make it one
        if isinstance(addr, Address):
            pass
        elif isinstance(addr, str):
            addr = LocalStation(addr)
        else:
            raise TypeError("addr must be a string or an Address")
        for fdte in self.bbmdFDT:
            if addr == fdte.fdAddress:
                break
        else:
            fdte = FDTEntry()
            fdte.fdAddress = addr
            self.bbmdFDT.append(fdte)
        fdte.fdTTL = ttl
        fdte.fdRemain = ttl + 5
        # return success
        return 0

    def delete_foreign_device_table_entry(self, addr):
        if DEBUG: _logger.debug("delete_foreign_device_table_entry %r", addr)
        # see if it is an address or make it one
        if isinstance(addr, Address):
            pass
        elif isinstance(addr, str):
            addr = LocalStation(addr)
        else:
            raise TypeError("addr must be a string or an Address")
        # find it and delete it
        stat = 0
        for i in range(len(self.bbmdFDT) - 1, -1, -1):
            if addr == self.bbmdFDT[i].fdAddress:
                del self.bbmdFDT[i]
                break
        else:
            stat = 99  ### entry not found
        # return status
        return stat

    def process_task(self):
        # look for foreign device registrations that have expired
        for i in range(len(self.bbmdFDT) - 1, -1, -1):
            fdte = self.bbmdFDT[i]
            fdte.fdRemain -= 1
            # delete it if it expired
            if fdte.fdRemain <= 0:
                if DEBUG: _logger.debug("foreign device expired: %r", fdte.fdAddress)
                del self.bbmdFDT[i]

    def add_peer(self, addr):
        if DEBUG: _logger.debug("add_peer %r", addr)
        # see if it is an address or make it one
        if isinstance(addr, Address):
            pass
        elif isinstance(addr, str):
            addr = LocalStation(addr)
        else:
            raise TypeError("addr must be a string or an Address")
        # if it's this BBMD, make it the first one
        if self.bbmdBDT and (addr == self.bbmdAddress):
            raise RuntimeError("add self to BDT as first address")
        # see if it's already there
        for bdte in self.bbmdBDT:
            if addr == bdte:
                break
        else:
            self.bbmdBDT.append(addr)

    def delete_peer(self, addr):
        if DEBUG: _logger.debug("delete_peer %r", addr)
        # see if it is an address or make it one
        if isinstance(addr, Address):
            pass
        elif isinstance(addr, str):
            addr = LocalStation(addr)
        else:
            raise TypeError("addr must be a string or an Address")
        # look for the peer address
        for i in range(len(self.bbmdBDT) - 1, -1, -1):
            if addr == self.bbmdBDT[i]:
                del self.bbmdBDT[i]
                break
        else:
            pass
