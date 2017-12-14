
import asyncore
import logging
import socket
import errno
from ..core import deferred
from ..comm import PDU

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['TCPServer']


class TCPServer(asyncore.dispatcher):

    def __init__(self, sock, peer):
        if DEBUG: _logger.debug("__init__ %r %r", sock, peer)
        # ToDo: Replace asyncore with asyncio
        asyncore.dispatcher.__init__(self, sock)
        # save the peer
        self.peer = peer
        # create a request buffer
        self.request = b''

    def handle_connect(self):
        if DEBUG: _logger.debug("handle_connect")

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
            if err.args[0] == errno.ECONNREFUSED:
                if DEBUG: _logger.debug("    - connection to %r refused", self.peer)
            else:
                if DEBUG: _logger.debug("    - recv socket error: %r", err)
            # pass along to a handler
            self.handle_error(err)

    def writable(self):
        return (len(self.request) != 0)

    def handle_write(self):
        if DEBUG: _logger.debug("handle_write")
        try:
            sent = self.send(self.request)
            if DEBUG: _logger.debug("    - sent %d octets, %d remaining", sent, len(self.request) - sent)
            self.request = self.request[sent:]
        except socket.error as err:
            if (err.args[0] == errno.ECONNREFUSED):
                if DEBUG: _logger.debug("    - connection to %r refused", self.peer)
            else:
                if DEBUG: _logger.debug("    - send socket error: %s", err)
            # sent the exception upstream
            self.handle_error(err)

    def handle_close(self):
        if DEBUG: _logger.debug("handle_close")
        if not self:
            if DEBUG: _logger.debug("    - self is None")
            return
        if not self.socket:
            if DEBUG: _logger.debug("    - socket already closed")
            return
        self.close()
        self.socket = None

    def handle_error(self, error=None):
        """Trap for TCPServer errors, otherwise continue."""
        if DEBUG: _logger.debug("handle_error %r", error)
        # core does not take parameters
        asyncore.dispatcher.handle_error(self)

    def indication(self, pdu):
        """Requests are queued for delivery."""
        if DEBUG: _logger.debug("indication %r", pdu)
        self.request += pdu.pduData
