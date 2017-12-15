
import asyncore
import socket
import errno
import logging

from ..core import deferred
from ..comm import PDU

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['TCPClient']

CONNECT_TIMEOUT = 30.0


class TCPClient(asyncore.dispatcher):
    """
    This class is a mapping between the client/server pattern and the socket API.
    The ctor is given the address to connect as a TCP client.
    Because objects of this class sit at the bottom of a protocol stack they are accessed as servers.
    """
    _connect_timeout = CONNECT_TIMEOUT

    def __init__(self, peer):
        raise NotImplementedError
        if DEBUG: _logger.debug("__init__ %r", peer)
        asyncore.dispatcher.__init__(self)
        # ask the dispatcher for a socket
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        # make sure the connection attempt is non-blocking
        self.socket.setblocking(0)
        if DEBUG: _logger.debug("    - non-blocking")
        # save the peer
        self.peer = peer
        self.connected = False
        # create a request buffer
        self.request = b''
        # try to connect
        try:
            rslt = self.socket.connect_ex(peer)
            if (rslt == 0):
                if DEBUG: _logger.debug("    - connected")
                self.connected = True
            elif rslt == errno.EINPROGRESS:
                if DEBUG: _logger.debug("    - in progress")
            elif rslt == errno.ECONNREFUSED:
                if DEBUG: _logger.debug("    - connection refused")
                self.handle_error(rslt)
            else:
                if DEBUG: _logger.debug("    - connect_ex: %r", rslt)
        except socket.error as err:
            if DEBUG: _logger.debug("    - connect socket error: %r", err)
            # pass along to a handler
            self.handle_error(err)

    def handle_accept(self):
        if DEBUG: _logger.debug("handle_accept")

    def handle_connect(self):
        if DEBUG: _logger.debug("handle_connect")
        self.connected = True

    def handle_connect_event(self):
        if DEBUG: _logger.debug("handle_connect_event")
        # there might be an error
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if DEBUG: _logger.debug("    - err: %r", err)
        # check for connection refused
        if (err == 0):
            if DEBUG: _logger.debug("    - no error")
            self.connected = True
        elif (err == errno.ECONNREFUSED):
            if DEBUG: _logger.debug("    - connection to %r refused", self.peer)
            self.handle_error(socket.error(errno.ECONNREFUSED, "connection refused"))
            return
        # pass along
        asyncore.dispatcher.handle_connect_event(self)

    def readable(self):
        return self.connected

    def handle_read(self):
        if DEBUG: _logger.debug("handle_read")
        try:
            msg = self.recv(65536)
            if DEBUG: _logger.debug("    - received %d octets", len(msg))
            # no socket means it was closed
            if not self.socket:
                if DEBUG: _logger.debug("    - socket was closed")
            else:
                # send the data upstream
                deferred(self.response, PDU(msg))

        except socket.error as err:
            if (err.args[0] == errno.ECONNREFUSED):
                if DEBUG: _logger.debug("    - connection to %r refused", self.peer)
            else:
                if DEBUG: _logger.debug("    - recv socket error: %r", err)
            # pass along to a handler
            self.handle_error(err)

    def writable(self):
        if not self.connected:
            return True
        return (len(self.request) != 0)

    def handle_write(self):
        if DEBUG: _logger.debug("handle_write")
        try:
            sent = self.send(self.request)
            if DEBUG: _logger.debug("    - sent %d octets, %d remaining", sent, len(self.request) - sent)
            self.request = self.request[sent:]
        except socket.error as err:
            if (err.args[0] == errno.EPIPE):
                if DEBUG: _logger.debug("    - broken pipe to %r", self.peer)
                return
            elif (err.args[0] == errno.ECONNREFUSED):
                if DEBUG: _logger.debug("    - connection to %r refused", self.peer)
            else:
                if DEBUG: _logger.debug("    - send socket error: %s", err)
            # pass along to a handler
            self.handle_error(err)

    def handle_write_event(self):
        if DEBUG: _logger.debug("handle_write_event")
        # there might be an error
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if DEBUG: _logger.debug("    - err: %r", err)
        # check for connection refused
        if err == 0:
            if not self.connected:
                if DEBUG: _logger.debug("    - connected")
                self.handle_connect()
        else:
            if DEBUG: _logger.debug("    - peer: %r", self.peer)
            if (err == errno.ECONNREFUSED):
                socket_error = socket.error(err, "connection refused")
            elif (err == errno.ETIMEDOUT):
                socket_error = socket.error(err, "timed out")
            elif (err == errno.EHOSTUNREACH):
                socket_error = socket.error(err, "host unreachable")
            else:
                socket_error = socket.error(err, "other unknown: %r" % (err,))
            if DEBUG: _logger.debug("    - socket_error: %r", socket_error)
            self.handle_error(socket_error)
            return
        # pass along
        asyncore.dispatcher.handle_write_event(self)

    def handle_close(self):
        if DEBUG: _logger.debug("handle_close")
        # close the socket
        self.close()
        # no longer connected
        self.connected = False
        # make sure other routines know the socket is closed
        self.socket = None

    def handle_error(self, error=None):
        """Trap for TCPClient errors, otherwise continue."""
        if DEBUG: _logger.debug("handle_error %r", error)
        # if there is no socket, it was closed
        if not self.socket:
            if DEBUG: _logger.debug("    - error already handled")
            return
        # core does not take parameters
        asyncore.dispatcher.handle_error(self)

    def indication(self, pdu):
        """Requests are queued for delivery."""
        if DEBUG: _logger.debug("indication %r", pdu)
        self.request += pdu.pduData
