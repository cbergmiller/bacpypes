import sys
import asyncio
import logging

from ..transport import UDPDirector
from ..comm import Client, Server, bind

from ..link import Address, LocalBroadcast, PDU, unpack_ip_addr

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['UDPMultiplexer']


class _MultiplexClient(Client):

    def __init__(self, mux):
        Client.__init__(self)
        self.multiplexer = mux

    def confirmation(self, pdu):
        self.multiplexer.confirmation(self, pdu)


class _MultiplexServer(Server):

    def __init__(self, mux):
        Server.__init__(self)
        self.multiplexer = mux

    def indication(self, pdu):
        self.multiplexer.indication(self, pdu)


class UDPMultiplexer:
    """
    UDPMultiplexer
    """

    def __init__(self, addr=None, noBroadcast=False):
        if DEBUG: _logger.debug('__init__ %r noBroadcast=%r', addr, noBroadcast)
        # check for some options
        special_broadcast = False
        if addr is None:
            self.address = Address()
            self.addrTuple = ('', 47808)
            self.addrBroadcastTuple = ('255.255.255.255', 47808)
        else:
            # allow the address to be cast
            if isinstance(addr, Address):
                self.address = addr
            else:
                self.address = Address(addr)
            # promote the normal and broadcast tuples
            self.addrTuple = self.address.addrTuple
            self.addrBroadcastTuple = self.address.addrBroadcastTuple
            # check for no broadcasting (loopback interface)
            if not self.addrBroadcastTuple:
                noBroadcast = True
            elif self.addrTuple == self.addrBroadcastTuple:
                # old school broadcast address
                self.addrBroadcastTuple = ('255.255.255.255', self.addrTuple[1])
            else:
                special_broadcast = True
        if DEBUG:
            _logger.debug('    - address: %r', self.address)
            _logger.debug('    - addrTuple: %r', self.addrTuple)
            _logger.debug('    - addrBroadcastTuple: %r', self.addrBroadcastTuple)
        # create and bind the direct address
        self.direct = _MultiplexClient(self)
        loop = asyncio.get_event_loop()
        listen = loop.create_datagram_endpoint(UDPDirector, local_addr=self.addrTuple, allow_broadcast=True)
        transport, protocol = loop.run_until_complete(listen)
        self.protocol = protocol
        bind(self.direct, protocol)
        # create and bind the broadcast address for non-Windows
        if special_broadcast and (not noBroadcast) and sys.platform in ('linux', 'darwin'):
            self.broadcast = _MultiplexClient(self)
            listen = loop.create_datagram_endpoint(
                UDPDirector,
                remote_addr=self.addrBroadcastTuple,
                reuse_address=True
            )
            transport, protocol = loop.run_until_complete(listen)
            self.broadcastProtocol = protocol
            bind(self.direct, self.broadcastProtocol)
        else:
            self.broadcast = None
            self.broadcastProtocol = None
        # create and bind the Annex H and J servers
        self.annexH = _MultiplexServer(self)
        self.annexJ = _MultiplexServer(self)

    def close_socket(self):
        if DEBUG: _logger.debug('close_socket')
        # pass along the close to the director(s)
        self.protocol.close_socket()
        if self.broadcastProtocol:
            self.broadcastProtocol.close_socket()

    def indication(self, server, pdu):
        if DEBUG: _logger.debug('indication %r %r', server, pdu)
        # check for a broadcast message
        if pdu.pduDestination.addrType == Address.localBroadcastAddr:
            dest = self.addrBroadcastTuple
            if DEBUG: _logger.debug('    - requesting local broadcast: %r', dest)
            # interface might not support broadcasts
            if not dest:
                return
        elif pdu.pduDestination.addrType == Address.localStationAddr:
            dest = unpack_ip_addr(pdu.pduDestination.addrAddr)
            if DEBUG: _logger.debug('    - requesting local station: %r', dest)
        else:
            raise RuntimeError('invalid destination address type')
        self.protocol.indication(PDU(pdu, destination=dest))

    def confirmation(self, client, pdu):
        if DEBUG: _logger.debug('confirmation %r %r', client, pdu)
        # if this came from ourselves, dump it
        if pdu.pduSource == self.addrTuple:
            if DEBUG: _logger.debug('    - from us!')
            return
        # the PDU source is a tuple, convert it to an Address instance
        src = Address(pdu.pduSource)
        # match the destination in case the stack needs it
        if client is self.direct:
            dest = self.address
        elif client is self.broadcast:
            dest = LocalBroadcast()
        else:
            raise RuntimeError('confirmation mismatch')
        # must have at least one octet
        if not pdu.pduData:
            if DEBUG: _logger.debug('    - no data')
            return
        # extract the first octet
        msg_type = pdu.pduData[0]
        # check for the message type
        if msg_type == 0x01:
            if self.annexH.serverPeer:
                self.annexH.response(PDU(pdu, source=src, destination=dest))
        elif msg_type == 0x81:
            if self.annexJ.serverPeer:
                self.annexJ.response(PDU(pdu, source=src, destination=dest))
        else:
            _logger.warning('unsupported message')
