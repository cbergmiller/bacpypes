#!/usr/bin/python

"""
Network Service
"""
import logging
from ..debugging import DebugContents
from ..comm import Client
from ..link import PDU
from .npdu import NPDU

# some debugging
DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['NetworkReference', 'RouterReference', 'NetworkAdapter']

# router status values
ROUTER_AVAILABLE = 0            # normal
ROUTER_BUSY = 1                 # router is busy
ROUTER_DISCONNECTED = 2         # could make a connection, but hasn't
ROUTER_UNREACHABLE = 3          # cannot route


class NetworkReference:
    """
    These objects map a network to a router.
    """

    def __init__(self, net, router, status):
        self.network = net
        self.router = router
        self.status = status


class RouterReference(DebugContents):
    """
    These objects map a router; the adapter to talk to it,
    its address, and a list of networks that it routes to.
    """

    _debug_contents = ('adapter-', 'address', 'networks', 'status')

    def __init__(self, adapter, addr, nets, status):
        self.adapter = adapter
        self.address = addr     # local station relative to the adapter
        self.networks = nets    # list of remote networks
        self.status = status    # status as presented by the router


class NetworkAdapter(Client, DebugContents):

    _debug_contents = ('adapterSAP-', 'adapterNet')

    def __init__(self, sap, net, cid=None):
        if DEBUG: _logger.debug("__init__ %r (net=%r) cid=%r", sap, net, cid)
        Client.__init__(self, cid)
        self.adapterSAP = sap
        self.adapterNet = net

        # add this to the list of adapters for the network
        sap.adapters.append(self)

    def confirmation(self, pdu):
        """Decode upstream PDUs and pass them up to the service access point."""
        if DEBUG: _logger.debug("confirmation %r (net=%r)", pdu, self.adapterNet)

        npdu = NPDU(user_data=pdu.pduUserData)
        npdu.decode(pdu)
        self.adapterSAP.process_npdu(self, npdu)

    def process_npdu(self, npdu):
        """Encode NPDUs from the service access point and send them downstream."""
        if DEBUG: _logger.debug("process_npdu %r (net=%r)", npdu, self.adapterNet)

        pdu = PDU(user_data=npdu.pduUserData)
        npdu.encode(pdu)
        self.request(pdu)

    def EstablishConnectionToNetwork(self, net):
        pass

    def DisconnectConnectionToNetwork(self, net):
        pass

