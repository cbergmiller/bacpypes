#!/usr/bin/python

"""
UDP Communications Module
"""

import asyncio
import logging

from ..core import deferred
from ..comm import PDU, Server, ServiceAccessPoint
from .udp_actor import UDPActor

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['UDPDirector']


class UDPDirector(asyncio.DatagramProtocol, Server, ServiceAccessPoint):
    """
    Network protocol for use with the AbstractEventLoop.create_datagram_endpoint() method.
    """
    def __init__(self, timeout=0, actor_class=UDPActor, sid=None, sapID=None, **kwargs):
        if DEBUG: _logger.debug(
            f'__init__ timeout={timeout} actorClass={actor_class!r} sid={sid} sapID={sapID} kwargs={kwargs!r}')
        Server.__init__(self, sid)
        ServiceAccessPoint.__init__(self, sapID)
        # check the actor class
        if not issubclass(actor_class, UDPActor):
            raise TypeError("actorClass must be a subclass of UDPActor")
        self.actorClass = actor_class
        # start with an empty peer pool
        self.peers = {}
        self.transport = None
        self.timeout = timeout

    def connection_made(self, transport):
        """Called by the event loop."""
        self.transport = transport

    def datagram_received(self, data, addr):
        """Called by the event loop."""
        if DEBUG: _logger.debug("    - received %d octets from %s", len(data), addr)
        # send the PDU up to the client
        deferred(self._response, PDU(data, source=addr))

    def error_received(self, exc):
        """Called by the event loop."""
        if exc.args[0] == 11:
            pass
        else:
            if DEBUG: _logger.debug("    - socket error: %s", exc)
            # pass along to a handler
            return
            # ToDo: handle error based on pdu destination
            # get the peer
            peer = self.peers.get(pdu.pduDestination, None)
            if peer:
                # let the actor handle the error
                peer.handle_error(err)
            else:
                # let the director handle the error
                self.handle_error(err)

    def connection_lost(self, exc):
        """Called by the event loop."""
        pass

    def add_actor(self, actor):
        """Add an actor when a new one is connected."""
        if DEBUG: _logger.debug("add_actor %r", actor)
        self.peers[actor.peer] = actor
        # tell the ASE there is a new client
        if self.serviceElement:
            self.sap_request(add_actor=actor)

    def del_actor(self, actor):
        """Remove an actor when the socket is closed."""
        if DEBUG: _logger.debug("del_actor %r", actor)
        del self.peers[actor.peer]
        # tell the ASE the client has gone away
        if self.serviceElement:
            self.sap_request(del_actor=actor)

    def actor_error(self, actor, error):
        if DEBUG: _logger.debug("actor_error %r %r", actor, error)
        # tell the ASE the actor had an error
        if self.serviceElement:
            self.sap_request(actor_error=actor, error=error)

    def get_actor(self, address):
        return self.peers.get(address, None)

    def close_socket(self):
        """Close the socket."""
        if DEBUG: _logger.debug("close_socket")
        self.transport.close()

    def send_request(self, pdu):
        _logger.info(f'upd send_request to {pdu.pduDestination}')
        self.transport.sendto(pdu.pduData, addr=pdu.pduDestination)

    def indication(self, pdu):
        """Client requests are queued for delivery."""
        if DEBUG: _logger.debug("indication %r", pdu)
        # get the destination
        addr = pdu.pduDestination
        # get the peer
        peer = self.peers.get(addr, None)
        if not peer:
            peer = self.actorClass(self, addr)
        # send the message
        peer.indication(pdu)

    def _response(self, pdu):
        """Incoming datagrams are routed through an actor."""
        if DEBUG: _logger.debug("_response %r", pdu)
        # get the destination
        addr = pdu.pduSource
        # get the peer
        peer = self.peers.get(addr, None)
        if not peer:
            peer = self.actorClass(self, addr)
        # send the message
        peer.response(pdu)
