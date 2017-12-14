
import time
import logging
from .tcp_client import TCPClient
from .pickle_actor_mixin import PickleActorMixIn
from ..task import call_later

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['TCPClientActor', 'TCPPickleClientActor']


class TCPClientActor(TCPClient):
    """
    Actors are helper objects for a director.  There is one actor for each connection.
    """
    def __init__(self, director, peer):
        if DEBUG: _logger.debug("__init__ %r %r", director, peer)
        # no director yet, no connection error
        self.director = None
        self._connection_error = None
        # add a timer
        self._connect_timeout = director.connect_timeout
        if self._connect_timeout:
            self.connect_timeout_handle = call_later(self._connect_timeout, self.connect_timeout)
        else:
            self.connect_timeout_handle = None
        # continue with initialization
        TCPClient.__init__(self, peer)
        # keep track of the director
        self.director = director
        # add a timer
        self._idle_timeout = director.idle_timeout
        if self._idle_timeout:
            self.idle_timeout_handle = call_later(self._idle_timeout, self.idle_timeout)
        else:
            self.idle_timeout_handle = None
        # this may have a flush state
        self.flush_task = None
        # tell the director this is a new actor
        self.director.add_actor(self)
        # if there was a connection error, pass it to the director
        if self._connection_error:
            if DEBUG: _logger.debug("    - had connection error")
            self.director.actor_error(self, self._connection_error)

    def handle_connect(self):
        if DEBUG: _logger.debug("handle_connect")
        # see if we are already connected
        if self.connected:
            if DEBUG: _logger.debug("    - already connected")
            return
        # if the connection timeout is scheduled, suspend it
        if self.connect_timeout_handle:
            if DEBUG: _logger.debug("    - canceling connection timeout")
            self.connect_timeout_handle.cancel()
            self.connect_timeout_handle = None
        # contine as expected
        TCPClient.handle_connect(self)

    def handle_error(self, error=None):
        """Trap for TCPClient errors, otherwise continue."""
        if DEBUG: _logger.debug("handle_error %r", error)
        # pass along to the director
        if error is not None:
            # this error may be during startup
            if not self.director:
                self._connection_error = error
            else:
                self.director.actor_error(self, error)
        else:
            TCPClient.handle_error(self)

    def handle_close(self):
        if DEBUG: _logger.debug("handle_close")

        # if there's a flush task, cancel it
        if self.flush_task:
            self.flush_task.suspend_task()
        # cancel the timers
        if self.connect_timeout_handle:
            if DEBUG: _logger.debug("    - canceling connection timeout")
            self.connect_timeout_handle.cancel()
            self.connect_timeout_handle = None
        if self.idle_timeout_handle:
            if DEBUG: _logger.debug("    - canceling idle timeout")
            self.idle_timeout_handle.cancel()
            self.idle_timeout_handle = None
        # tell the director this is gone
        self.director.del_actor(self)
        # pass the function along
        TCPClient.handle_close(self)

    def connect_timeout(self):
        if DEBUG: _logger.debug("connect_timeout")
        # shut it down
        self.handle_close()

    def idle_timeout(self):
        if DEBUG: _logger.debug("idle_timeout")
        # shut it down
        self.handle_close()

    def indication(self, pdu):
        if DEBUG: _logger.debug("indication %r", pdu)
        # additional downstream data is tossed while flushing
        if self.flush_task:
            if DEBUG: _logger.debug("    - flushing")
            return
        # reschedule the timer
        if self.idle_timeout_handle:
            self.idle_timeout_handle.install_task(time.time() + self._idle_timeout)
        # continue as usual
        TCPClient.indication(self, pdu)

    def response(self, pdu):
        if DEBUG: _logger.debug("response %r", pdu)
        # put the peer address in as the source
        pdu.pduSource = self.peer
        # reschedule the timer
        if self.idle_timeout_handle:
            self.idle_timeout_handle.install_task(time.time() + self._idle_timeout)
        # process this as a response from the director
        self.director.response(pdu)

    def flush(self):
        if DEBUG: _logger.debug("flush")
        # clear out the old task
        self.flush_task = None
        # if the outgoing buffer has data, re-schedule another attempt
        if self.request:
            self.flush_task = call_later(0.001, self.flush)
            return
        # close up shop, all done
        self.handle_close()


class TCPPickleClientActor(PickleActorMixIn, TCPClientActor):
    pass
