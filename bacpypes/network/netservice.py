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
__all__ = ['RouterInfo', 'RouterInfoCache', 'NetworkAdapter']

# router status values
ROUTER_AVAILABLE = 0            # normal
ROUTER_BUSY = 1                 # router is busy
ROUTER_DISCONNECTED = 2         # could make a connection, but hasn't
ROUTER_UNREACHABLE = 3          # cannot route


class RouterInfo(DebugContents):
    """These objects are routing information records that map router
    addresses with destination networks."""

    _debug_contents = ('snet', 'address', 'dnets', 'status')

    def __init__(self, snet, address, dnets, status=ROUTER_AVAILABLE):
        self.snet = snet        # source network
        self.address = address  # address of the router
        self.dnets = dnets      # list of reachable networks through this router
        self.status = status    # router status


class RouterInfoCache:

    def __init__(self):
        if DEBUG: _logger.debug("__init__")

        self.routers = {}           # (snet, address) -> RouterInfo
        self.networks = {}          # network -> RouterInfo

    def get_router_info(self, dnet):
        if DEBUG: _logger.debug("get_router_info %r", dnet)

        # check to see if we know about it
        if dnet not in self.networks:
            if DEBUG: _logger.debug("   - no route")
            return None

        # return the network and address
        router_info = self.networks[dnet]
        if DEBUG: _logger.debug("   - router_info: %r", router_info)

        # return the network, address, and status
        return (router_info.snet, router_info.address, router_info.status)

    def update_router_info(self, snet, address, dnets):
        if DEBUG: _logger.debug("update_router_info %r %r %r", snet, address, dnets)

        # look up the router reference, make a new record if necessary
        key = (snet, address)
        if key not in self.routers:
            if DEBUG: _logger.debug("   - new router")
            router_info = self.routers[key] = RouterInfo(snet, address, list())
        else:
            router_info = self.routers[key]

        # add (or move) the destination networks
        for dnet in dnets:
            if dnet in self.networks:
                other_router = self.networks[dnet]
                if other_router is router_info:
                    if DEBUG: _logger.debug("   - existing router, match")
                    continue
                elif dnet not in other_router.dnets:
                    if DEBUG: _logger.debug("   - where did it go?")
                else:
                    other_router.dnets.remove(dnet)
                    if not other_router.dnets:
                        if DEBUG: _logger.debug("    - no longer care about this router")
                        del self.routers[(snet, other_router.address)]

            # add a reference to the router
            self.networks[dnet] = router_info
            if DEBUG: _logger.debug("   - reference added")

            # maybe update the list of networks for this router
            if dnet not in router_info.dnets:
                router_info.dnets.append(dnet)
                if DEBUG: _logger.debug("   - dnet added, now: %r", router_info.dnets)

    def update_router_status(self, snet, address, status):
        if DEBUG: _logger.debug("update_router_status %r %r %r", snet, address, status)

        key = (snet, address)
        if key not in self.routers:
            if DEBUG: _logger.debug("   - not a router we care about")
            return

        router_info = self.routers[key]
        router_info.status = status
        if DEBUG: _logger.debug("   - status updated")

    def delete_router_info(self, snet, address=None, dnets=None):
        if DEBUG: _logger.debug("delete_router_info %r %r %r", dnets)

        # if address is None, remove all the routers for the network
        if address is None:
            for rnet, raddress in self.routers.keys():
                if snet == rnet:
                    if DEBUG: _logger.debug("   - going down")
                    self.delete_router_info(snet, raddress)
            if DEBUG: _logger.debug("   - back topside")
            return

        # look up the router reference
        key = (snet, address)
        if key not in self.routers:
            if DEBUG: _logger.debug("   - unknown router")
            return

        router_info = self.routers[key]
        if DEBUG: _logger.debug("   - router_info: %r", router_info)

        # if dnets is None, remove all the networks for the router
        if dnets is None:
            dnets = router_info.dnets

        # loop through the list of networks to be deleted
        for dnet in dnets:
            if dnet in self.networks:
                del self.networks[dnet]
                if DEBUG: _logger.debug("   - removed from networks: %r", dnet)
            if dnet in router_info.dnets:
                router_info.dnets.remove(dnet)
                if DEBUG: _logger.debug("   - removed from router_info: %r", dnet)

        # see if we still care
        if not router_info.dnets:
            if DEBUG: _logger.debug("    - no longer care about this router")
            del self.routers[key]


class NetworkAdapter(Client, DebugContents):

    _debug_contents = ('adapterSAP-', 'adapterNet')

    def __init__(self, sap, net, cid=None):
        if DEBUG: _logger.debug('__init__ %r (net=%r) cid=%r', sap, net, cid)
        Client.__init__(self, cid)
        self.adapterSAP = sap
        self.adapterNet = net

    def confirmation(self, pdu):
        """Decode upstream PDUs and pass them up to the service access point."""
        if DEBUG: _logger.debug('confirmation %r (net=%r)', pdu, self.adapterNet)
        npdu = NPDU(user_data=pdu.pduUserData)
        npdu.decode(pdu)
        self.adapterSAP.process_npdu(self, npdu)

    def process_npdu(self, npdu):
        """Encode NPDUs from the service access point and send them downstream."""
        if DEBUG: _logger.debug('process_npdu %r (net=%r)', npdu, self.adapterNet)
        pdu = PDU(user_data=npdu.pduUserData)
        npdu.encode(pdu)
        self.request(pdu)

    def EstablishConnectionToNetwork(self, net):
        pass

    def DisconnectConnectionToNetwork(self, net):
        pass

