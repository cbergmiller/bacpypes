
import logging

from ..comm import ApplicationServiceElement
from ..link import Address
from .connection_state import ConnectionState

_logger = logging.getLogger(__name__)
__all__ = ['TCPMultiplexerASE']


class TCPMultiplexerASE(ApplicationServiceElement):
    """
    TCPMultiplexerASE
    """

    def __init__(self, mux):
        # keep track of the multiplexer
        self.multiplexer = mux
        # ToDo: why is the call to __init__ of the base class missing here?

    def indication(self, *args, **kwargs):
        if 'addPeer' in kwargs:
            addr = Address(kwargs['addPeer'])
            if addr in self.multiplexer.connections:
                # already a connection
                return
            conn = ConnectionState(addr)
            # add it to the multiplexer connections
            self.multiplexer.connections[addr] = conn

        if 'delPeer' in kwargs:
            addr = Address(kwargs['delPeer'])
            if addr not in self.multiplexer.connections:
                # not a connection
                return
            # get the connection
            conn = self.multiplexer.connections.get(addr)
            # if it is associated and connected, disconnect it
            if conn.service and conn.connected:
                conn.service.remove_connection(conn)
            # remove it from the multiplexer
            del self.multiplexer.connections[addr]
