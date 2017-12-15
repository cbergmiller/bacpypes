
import logging
from .ioq_controller import IOQController

_logger = logging.getLogger(__name__)
__all__ = ['SieveQueue']


class SieveQueue(IOQController):

    def __init__(self, request_fn, address=None):
        _logger.debug("__init__ %r %r", request_fn, address)
        IOQController.__init__(self, str(address))
        # save a reference to the request function
        self.request_fn = request_fn
        self.address = address

    def process_io(self, iocb):
        _logger.debug("process_io %r", iocb)
        # this is now an active request
        self.active_io(iocb)
        # send the request
        self.request_fn(iocb.args[0])
