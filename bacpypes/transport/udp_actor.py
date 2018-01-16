
import pickle
import logging

from ..task import call_later


DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['UDPActor', 'UDPPickleActor']


class UDPActor:
    """
    UDPActor
    Actors are helper objects for a director.
    There is one actor for each peer.
    """
    def __init__(self, director, peer):
        if DEBUG: _logger.debug("__init__ %r %r", director, peer)
        self.director = director
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
            _logger.exception("pickle error")
            return
        # continue as usual
        UDPActor.response(self, pdu)