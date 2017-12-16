
import logging
from .ioq_controller import IOQController
from .client import Client

_logger = logging.getLogger(__name__)
__all__ = ['IOQController']


class ClientController(Client, IOQController):
    """
    An instance of this class is a controller that sits at the top of a
    protocol stack as a client.  The IOCBs to be processed contain a single
    PDU parameter that is sent down the stack.  Any PDU coming back up
    the stack is assumed to complete the current request.

    This class is used for protocol stacks with a strict master/slave
    architecture.

    This class inherits from `IOQController` so if there is already an active
    request then subsequent requests are queued.
    """
    def __init__(self):
        _logger.debug("__init__")
        Client.__init__(self)
        IOQController.__init__(self)

    def _process_io(self, iocb):
        _logger.debug("process_io %r", iocb)
        # this is now an active request
        self.active_io(iocb)
        # send the PDU downstream
        self.request(iocb.args[0])

    def confirmation(self, pdu):
        _logger.debug("confirmation %r", pdu)
        # make sure it has an active iocb
        if not self.active_iocb:
            _logger.debug("no active request")
            return
        # look for exceptions
        if isinstance(pdu, Exception):
            self.abort_io(self.active_iocb, pdu)
        else:
            self.complete_io(self.active_iocb, pdu)
