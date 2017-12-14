#!/usr/bin/python

"""
UDP Communications Module
"""

import asyncio
import pickle
import logging
from time import time as _time

from .debugging import ModuleLogger, bacpypes_debugging

from .core import deferred
from .task import call_later
from .comm import PDU, Server
from .comm import ServiceAccessPoint

DEBUG = True
_logger = logging.getLogger(__name__)


class UDPActor:
    """
    UDPActor
    Actors are helper objects for a director.  There is one actor for each peer.
    """
    def __init__(self, director, peer):
        if DEBUG: _logger.debug("__init__ %r %r", director, peer)

        # keep track of the director
        self.director = director

        # associated with a peer
        self.peer = peer

        # add a timer
        self.timeout = director.timeout
        if self.timeout > 0:
            self.timeout_handle = call_later(self.timeout, self.idle_timeout)
        else:
            self.timeout_handle = None

        # tell the director this is a new actor
        self.director.add_actor(self)

    def idle_timeout(self):
        if DEBUG: _logger.debug("idle_timeout")

        # tell the director this is gone
        self.director.del_actor(self)

    def indication(self, pdu):
        if DEBUG: _logger.debug("indication %r", pdu)

        # reschedule the timer
        if self.timeout_handle:
            self.timeout_handle.cancel()
            self.timeout_handle = call_later(self.timeout, self.idle_timeout)

        # put it in the outbound queue for the director
        self.director.send_request(pdu)

    def response(self, pdu):
        if DEBUG: _logger.debug("response %r", pdu)

        # reschedule the timer
        if self.timeout_handle:
            self.timeout_handle.cancel()
            self.timeout_handle = call_later(self.timeout, self.idle_timeout)

        # process this as a response from the director
        self.director.response(pdu)

    def handle_error(self, error=None):
        if DEBUG: _logger.debug("handle_error %r", error)

        # pass along to the director
        if error is not None:
            self.director.actor_error(self, error)


#
#   UDPPickleActor
#

@bacpypes_debugging
class UDPPickleActor(UDPActor):

    def __init__(self, *args):
        if DEBUG: _logger.debug("__init__ %r", args)
        UDPActor.__init__(self, *args)

    def indication(self, pdu):
        if DEBUG: _logger.debug("indication %r", pdu)

        # pickle the data
        pdu.pduData = pickle.dumps(pdu.pduData)

        # continue as usual
        UDPActor.indication(self, pdu)

    def response(self, pdu):
        if DEBUG: _logger.debug("response %r", pdu)

        # unpickle the data
        try:
            pdu.pduData = pickle.loads(pdu.pduData)
        except:
            UDPPickleActor._exception("pickle error")
            return

        # continue as usual
        UDPActor.response(self, pdu)


#
#   UDPDirector
#

@bacpypes_debugging
class UDPDirector(asyncio.DatagramProtocol, Server, ServiceAccessPoint):
    """
    Protocol Factory for use with the AbstractEventLoop.create_datagram_endpoint() method.
    """
    def __init__(self, timeout=0, actorClass=UDPActor, sid=None, sapID=None, **kwargs):
        if DEBUG: _logger.debug(f'__init__ timeout={timeout} actorClass={actorClass!r} sid={sid} sapID={sapID} kwargs={kwargs!r}')
        Server.__init__(self, sid)
        ServiceAccessPoint.__init__(self, sapID)
        # check the actor class
        if not issubclass(actorClass, UDPActor):
            raise TypeError("actorClass must be a subclass of UDPActor")
        self.actorClass = actorClass
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
        self.transport.sendto(pdu.pduData, pdu.pduDestination)

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
