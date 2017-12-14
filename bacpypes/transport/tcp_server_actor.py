
import logging
from .tcp_server import TCPServer
from .pickle_actor_mixin import PickleActorMixIn
from ..task import call_later

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['TCPServerActor', 'TCPPickleServerActor']


class TCPServerActor(TCPServer):

    def __init__(self, director, sock, peer):
        if DEBUG: _logger.debug("__init__ %r %r %r", director, sock, peer)
        TCPServer.__init__(self, sock, peer)
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

    def handle_error(self, error=None):
        """Trap for TCPServer errors, otherwise continue."""
        if DEBUG: _logger.debug("handle_error %r", error)
        # pass along to the director
        if error is not None:
            self.director.actor_error(self, error)
        else:
            TCPServer.handle_error(self)

    def handle_close(self):
        if DEBUG: _logger.debug("handle_close")
        # if there's a flush task, cancel it
        if self.flush_task:
            self.flush_task.suspend_task()
        # if there is an idle timeout, cancel it
        if self.idle_timeout_handle:
            if DEBUG: _logger.debug("    - canceling idle timeout")
            self.idle_timeout_handle.cancel()
            self.idle_timeout_handle = None
        # tell the director this is gone
        self.director.del_actor(self)
        # pass it down
        TCPServer.handle_close(self)

    def idle_timeout(self):
        if DEBUG: _logger.debug("idle_timeout")
        self.idle_timeout_handle = None
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
            self.idle_timeout_handle.cancel()
            self.idle_timeout_handle = call_later(self._idle_timeout, self.idle_timeout)
        # continue as usual
        TCPServer.indication(self, pdu)

    def response(self, pdu):
        if DEBUG: _logger.debug("response %r", pdu)
        # upstream data is tossed while flushing
        if self.flush_task:
            if DEBUG: _logger.debug("    - flushing")
            return
        # save the source
        pdu.pduSource = self.peer
        # reschedule the timer
        if self.idle_timeout_handle:
            self.idle_timeout_handle.cancel()
            self.idle_timeout_handle = call_later(self._idle_timeout, self.idle_timeout)
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

class TCPPickleServerActor(PickleActorMixIn, TCPServerActor):
    pass
