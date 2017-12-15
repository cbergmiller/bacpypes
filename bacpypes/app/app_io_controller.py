
import logging
from ..comm import IOController, SieveQueue, IOCB

from ..apdu import UnconfirmedRequestPDU, SimpleAckPDU, ComplexAckPDU, ErrorPDU, RejectPDU, AbortPDU
from .app import Application

_logger = logging.getLogger(__name__)
__all__ = ['ApplicationIOController']


class ApplicationIOController(IOController, Application):
    """
    ApplicationIOController
    """
    def __init__(self, *args, **kwargs):
        IOController.__init__(self)
        Application.__init__(self, *args, **kwargs)
        # queues for each address
        self.queue_by_address = {}

    def process_io(self, iocb: IOCB):
        # get the destination address from the pdu
        destination_address = iocb.args[0].pduDestination
        # look up the queue
        queue = self.queue_by_address.get(destination_address, None)
        if not queue:
            queue = SieveQueue(self.request, destination_address)
            self.queue_by_address[destination_address] = queue
        # ask the queue to process the request
        queue.request_io(iocb)

    def _app_complete(self, address, apdu):
        # look up the queue
        queue = self.queue_by_address.get(address, None)
        if not queue:
            _logger.debug(f'no queue for {address!r}')
            return
        # make sure it has an active iocb
        if not queue.active_iocb:
            _logger.debug(f'no active request for {address!r}')
            return
        # this request is complete
        if isinstance(apdu, (None.__class__, SimpleAckPDU, ComplexAckPDU)):
            queue.complete_io(queue.active_iocb, apdu)
        elif isinstance(apdu, (ErrorPDU, RejectPDU, AbortPDU)):
            queue.abort_io(queue.active_iocb, apdu)
        else:
            raise RuntimeError('unrecognized APDU type')
        # if the queue is empty and idle, forget about the controller
        if not queue.ioQueue.queue and not queue.active_iocb:
            del self.queue_by_address[address]

    def request(self, apdu):
        # send it downstream
        super(ApplicationIOController, self).request(apdu)
        # if this was an unconfirmed request, it's complete, no message
        if isinstance(apdu, UnconfirmedRequestPDU):
            self._app_complete(apdu.pduDestination, None)

    def confirmation(self, apdu):
        # this is an ack, error, reject or abort
        self._app_complete(apdu.pduSource, apdu)
