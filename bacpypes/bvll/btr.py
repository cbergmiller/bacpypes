
import logging
from ..debugging import DebugContents
from ..comm import Client, Server
from ..link import Address, PDU

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['BTR']


class BTR(Client, Server, DebugContents):

    _debug_contents = ('peers+',)

    def __init__(self, cid=None, sid=None):
        """An Annex-H BACnet Tunneling Router node."""
        if DEBUG: _logger.debug('__init__ cid=%r sid=%r', cid, sid)
        Client.__init__(self, cid)
        Server.__init__(self, sid)
        # initialize a dicitonary of peers
        self.peers = {}

    def indication(self, pdu):
        if DEBUG: _logger.debug('indication %r', pdu)
        # check for local stations
        if pdu.pduDestination.addrType == Address.localStationAddr:
            # make sure it is going to a peer
            if pdu.pduDestination not in self.peers:
                ### log this
                return
            # send it downstream
            self.request(pdu)
        # check for broadcasts
        elif pdu.pduDestination.addrType == Address.localBroadcastAddr:
            # loop through the peers
            for peerAddr in self.peers.keys():
                xpdu = PDU(pdu.pduData, destination=peerAddr)
                # send it downstream
                self.request(xpdu)
        else:
            raise RuntimeError('invalid destination address type (2)')

    def confirmation(self, pdu):
        if DEBUG: _logger.debug('confirmation %r', pdu)
        # make sure it came from a peer
        if pdu.pduSource not in self.peers:
            _logger.warning('not a peer: %r', pdu.pduSource)
            return
        # send it upstream
        self.response(pdu)

    def add_peer(self, peerAddr, networks=None):
        """Add a peer and optionally provide a list of the reachable networks."""
        if DEBUG: _logger.debug('add_peer %r networks=%r', peerAddr, networks)
        # see if this is already a peer
        if peerAddr in self.peers:
            # add the (new?) reachable networks
            if not networks:
                networks = []
            else:
                self.peers[peerAddr].extend(networks)
        else:
            if not networks:
                networks = []
            # save the networks
            self.peers[peerAddr] = networks
        ### send a control message upstream that these are reachable

    def delete_peer(self, peerAddr):
        """Delete a peer."""
        if DEBUG: _logger.debug('delete_peer %r', peerAddr)
        # get the peer networks
        # networks = self.peers[peerAddr]
        ### send a control message upstream that these are no longer reachable
        # now delete the peer
        del self.peers[peerAddr]
