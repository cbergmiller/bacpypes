
import asyncio
import logging
from collections import defaultdict
from .iocb_states import *
from .io_controller import IOController
from .iocb import IOCB

_logger = logging.getLogger(__name__)
__all__ = ['IOQController']


class IOQController(IOController):
    """
    Queued IO Controller
    An `IOQController` has an identical interface as the `IOContoller`,
    but provides additional hooks to make sure that only one IOCB is
    being processed at a time for each destination address.
    """

    def __init__(self, name=None):
        """Initialize a queue controller."""
        _logger.debug('__init__ name=%r', name)
        IOController.__init__(self, name)
        # queues for each destination
        self.address_queues = defaultdict(lambda: asyncio.PriorityQueue())

    def request_io(self, iocb: IOCB):
        """
        This method is called by the application requesting the service of a
        controller.  If the controller is already busy processing a request,
        this IOCB is queued until the current processing is complete.
        :param iocb: the IOCB to be processed
        """
        _logger.debug('request_io %r', iocb)
        if not isinstance(iocb, IOCB):
            raise TypeError('IOCB expected')
        iocb.io_controller = self
        iocb.io_state = PENDING
        self._put_to_queue(iocb)

    def _put_to_queue(self, iocb: IOCB):
        destination_address = iocb.request.pduDestination
        # if there is no queue for this address yet, it will be constructed by the defaultdict
        queue = self.address_queues[destination_address]
        if queue.empty():
            _logger.debug('start new IO Queue Consumer for %r', destination_address)
            asyncio.get_event_loop().create_task(self._process_queue(destination_address))
        queue.put_nowait(iocb)

    async def _process_queue(self, destination_address):
        """
        Sequentially process IOCBs from the address queue.
        """
        queue = self.address_queues[destination_address]
        while True:
            iocb = await queue.get()
            if iocb.io_state != ABORTED:
                try:
                    # let derived class figure out how to process this
                    self._process_io(iocb)
                    await iocb.wait()
                except Exception as e:
                    # if there was an error, abort the request
                    self.abort_io(iocb, e)
            queue.task_done()
            if queue.empty():
                _logger.debug('exiting IO Queue Consumer for %r', destination_address)
                break

    def _process_io(self, iocb: IOCB):
        """Figure out how to respond to this request.  This must be provided by the derived class."""
        raise NotImplementedError('IOController must implement process_io()')

