
import logging
from .io_controller import IOController
from .sieve_queue import SieveQueue
from .client import Client

_logger = logging.getLogger(__name__)
__all__ = ['SieveClientController']


class SieveClientController(Client, IOController):

    def __init__(self, queue_class=SieveQueue):
        _logger.debug("__init__")
        Client.__init__(self)
        IOController.__init__(self)
        # make sure it's the correct class
        if not issubclass(queue_class, SieveQueue):
            raise TypeError("queue class must be a subclass of SieveQueue")
        # queues for each address
        self.queues = {}
        self.queue_class = queue_class

    def process_io(self, iocb):
        _logger.debug("process_io %r", iocb)
        # get the destination address from the pdu
        destination_address = iocb.args[0].pduDestination
        _logger.debug("    - destination_address: %r", destination_address)
        # look up the queue
        queue = self.queues.get(destination_address, None)
        if not queue:
            _logger.debug("    - new queue")
            queue = self.queue_class(self.request, destination_address)
            self.queues[destination_address] = queue
        _logger.debug("    - queue: %r", queue)
        # ask the queue to process the request
        queue.request_io(iocb)

    def request(self, pdu):
        _logger.debug("request %r", pdu)
        # send it downstream
        super(SieveClientController, self).request(pdu)

    def confirmation(self, pdu):
        _logger.debug("confirmation %r", pdu)
        # get the source address
        source_address = pdu.pduSource
        _logger.debug("    - source_address: %r", source_address)
        # look up the queue
        queue = self.queues.get(source_address, None)
        if not queue:
            _logger.debug("    - no queue: %r" % (source_address,))
            return
        _logger.debug("    - queue: %r", queue)
        # make sure it has an active iocb
        if not queue.active_iocb:
            _logger.debug("    - no active request")
            return
        # complete the request
        if isinstance(pdu, Exception):
            queue.abort_io(queue.active_iocb, pdu)
        else:
            queue.complete_io(queue.active_iocb, pdu)
        # if the queue is empty and idle, forget about the controller
        if not queue.io_queue.queue and not queue.active_iocb:
            _logger.debug("    - queue is empty")
            del self.queues[source_address]
