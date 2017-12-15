
import logging
from ..debugging import DebugContents
from ..task import call_later
from ..comm import Server, ServiceAccessPoint
from .tcp_client_actor import TCPClientActor

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['TCPClientDirector']


class TCPClientDirector(Server, ServiceAccessPoint, DebugContents):
    """
    A client director presents a connection pool as one virtual
    interface.  If a request should be sent to an address and there
    is no connection already established for it, it will create one
    and maintain it.  PDU's from TCP clients have no source address,
    so one is provided by the client actor.
    """
    _debug_contents = ('connect_timeout', 'idle_timeout', 'actorClass', 'clients', 'reconnect')

    def __init__(self, connect_timeout=None, idle_timeout=None, actorClass=TCPClientActor, sid=None, sapID=None):
        raise NotImplementedError
        if DEBUG:
            _logger.debug("__init__ connect_timeout=%r idle_timeout=%r actorClass=%r sid=%r sapID=%r",
            connect_timeout, idle_timeout, actorClass, sid, sapID,
            )
        Server.__init__(self, sid)
        ServiceAccessPoint.__init__(self, sapID)
        # check the actor class
        if not issubclass(actorClass, TCPClientActor):
            raise TypeError("actorClass must be a subclass of TCPClientActor")
        self.actorClass = actorClass
        # save the timeout for actors
        self.connect_timeout = connect_timeout
        self.idle_timeout = idle_timeout
        # start with an empty client pool
        self.clients = {}
        # no clients automatically reconnecting
        self.reconnect = {}

    def add_actor(self, actor):
        """Add an actor when a new one is connected."""
        if DEBUG: _logger.debug("add_actor %r", actor)
        self.clients[actor.peer] = actor
        # tell the ASE there is a new client
        if self.serviceElement:
            self.sap_request(add_actor=actor)

    def del_actor(self, actor):
        """Remove an actor when the socket is closed."""
        if DEBUG: _logger.debug("del_actor %r", actor)
        # delete the client
        del self.clients[actor.peer]
        # tell the ASE the client has gone away
        if self.serviceElement:
            self.sap_request(del_actor=actor)
        # see if it should be reconnected
        if actor.peer in self.reconnect:
            call_later(self.reconnect[actor.peer], self.connect, actor.peer)

    def actor_error(self, actor, error):
        if DEBUG: _logger.debug("actor_error %r %r", actor, error)
        # tell the ASE the actor had an error
        if self.serviceElement:
            self.sap_request(actor_error=actor, error=error)

    def get_actor(self, address):
        """ Get the actor associated with an address or None. """
        return self.clients.get(address, None)

    def connect(self, address, reconnect=0):
        if DEBUG: _logger.debug("connect %r reconnect=%r", address, reconnect)
        if address in self.clients:
            return
        # create an actor, which will eventually call add_actor
        client = self.actorClass(self, address)
        if DEBUG: _logger.debug("    - client: %r", client)
        # if it should automatically reconnect, save the timer value
        if reconnect:
            self.reconnect[address] = reconnect

    def disconnect(self, address):
        if DEBUG: _logger.debug("disconnect %r", address)
        if address not in self.clients:
            return
        # if it would normally reconnect, don't bother
        if address in self.reconnect:
            del self.reconnect[address]
        # close it
        self.clients[address].handle_close()

    def indication(self, pdu):
        """Direct this PDU to the appropriate server, create a
        connection if one hasn't already been created."""
        if DEBUG: _logger.debug("indication %r", pdu)
        # get the destination
        addr = pdu.pduDestination
        # get the client
        client = self.clients.get(addr, None)
        if not client:
            client = self.actorClass(self, addr)
        # send the message
        client.indication(pdu)
