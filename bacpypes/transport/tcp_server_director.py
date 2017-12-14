
import logging
import asyncore
import socket
from ..debugging import DebugContents
from ..comm import Server, ServiceAccessPoint
from .tcp_server_actor import TCPServerActor

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['TCPServerDirector']

REBIND_SLEEP_INTERVAL = 2.0


class TCPServerDirector(asyncore.dispatcher, Server, ServiceAccessPoint, DebugContents):

    _debug_contents = ('port', 'idle_timeout', 'actorClass', 'servers')

    def __init__(self, address, listeners=5, idle_timeout=0, reuse=False, actorClass=TCPServerActor, cid=None, sapID=None):
        if DEBUG:
            _logger.debug("__init__ %r listeners=%r idle_timeout=%r reuse=%r actorClass=%r cid=%r sapID=%r"
                , address, listeners, idle_timeout, reuse, actorClass, cid, sapID
                )
        Server.__init__(self, cid)
        ServiceAccessPoint.__init__(self, sapID)
        # save the address and timeout
        self.port = address
        self.idle_timeout = idle_timeout
        # check the actor class
        if not issubclass(actorClass, TCPServerActor):
            raise TypeError("actorClass must be a subclass of TCPServerActor")
        self.actorClass = actorClass
        # start with an empty pool of servers
        self.servers = {}
        # continue with initialization
        asyncore.dispatcher.__init__(self)
        # create a listening port
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        if reuse:
            self.set_reuse_addr()
        # try to bind, keep trying for a while if its already in use
        hadBindErrors = False
        for i in range(30):
            try:
                self.bind(address)
                break
            except socket.error as err:
                hadBindErrors = True
                _logger.warning('bind error %r, sleep and try again', err)
                _sleep(REBIND_SLEEP_INTERVAL)
        else:
            _logger.error('unable to bind')
            raise RuntimeError("unable to bind")

        # if there were some bind errors, generate a meesage that all is OK now
        if hadBindErrors:
            _logger.info('bind successful')
        self.listen(listeners)

    def handle_accept(self):
        if DEBUG: _logger.debug("handle_accept")
        try:
            client, addr = self.accept()
        except socket.error:
            _logger.warning('accept() threw an exception')
            return
        except TypeError:
            _logger.warning('accept() threw EWOULDBLOCK')
            return
        if DEBUG: _logger.debug("    - connection %r, %r", client, addr)
        # create a server
        server = self.actorClass(self, client, addr)
        # add it to our pool
        self.servers[addr] = server
        # return it to the dispatcher
        return server

    def handle_close(self):
        if DEBUG: _logger.debug("handle_close")
        # close the socket
        self.close()

    def add_actor(self, actor):
        if DEBUG: _logger.debug("add_actor %r", actor)
        self.servers[actor.peer] = actor
        # tell the ASE there is a new server
        if self.serviceElement:
            self.sap_request(add_actor=actor)

    def del_actor(self, actor):
        if DEBUG: _logger.debug("del_actor %r", actor)
        try:
            del self.servers[actor.peer]
        except KeyError:
            _logger.warning("del_actor: %r not an actor", actor)
        # tell the ASE the server has gone away
        if self.serviceElement:
            self.sap_request(del_actor=actor)

    def actor_error(self, actor, error):
        if DEBUG: _logger.debug("actor_error %r %r", actor, error)
        # tell the ASE the actor had an error
        if self.serviceElement:
            self.sap_request(actor_error=actor, error=error)

    def get_actor(self, address):
        """ Get the actor associated with an address or None. """
        return self.servers.get(address, None)

    def indication(self, pdu):
        """Direct this PDU to the appropriate server."""
        if DEBUG: _logger.debug("indication %r", pdu)
        # get the destination
        addr = pdu.pduDestination
        # get the server
        server = self.servers.get(addr, None)
        if not server:
            raise RuntimeError("not a connected server")
        # pass the indication to the actor
        server.indication(pdu)
