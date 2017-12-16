
import logging
from .ioq_controller import IOQController

_logger = logging.getLogger(__name__)
__all__ = ['SieveQueue']


class SieveQueue(IOQController):
    """
    Queued IO Controller that passes requests back to the controller that manages the queues.
    """
    def __init__(self, master_controller, address=None):
        _logger.debug("__init__ %r %r", master_controller, address)
        assert hasattr(master_controller, 'request')
        IOQController.__init__(self, str(address))
        # save a reference to the request function
        self.master_controller = master_controller
        self.address = address

    def _process_io(self, iocb):
        _logger.debug("process_io %r", iocb)
        # this is now an active request
        self.active_io(iocb)
        # send the request
        self.master_controller.request(iocb.args[0])
