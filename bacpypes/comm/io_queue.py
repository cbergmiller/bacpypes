
import logging
import threading
from .iocb_states import *
from .iocb import IOCB
from asyncio import PriorityQueue

_logger = logging.getLogger(__name__)
__all__ = ['IOQueue']


class IOQueue:

    def __init__(self, name=None):
        _logger.debug(f'__init__ name={name!r}')
        self.queue = PriorityQueue()

    @property
    def empty(self):
        return self.queue.empty()

    def put(self, iocb: IOCB):
        """
        Add an IOCB to a queue. This is usually called by the function that filters
        requests and passes them out to the correct processing thread.
        """
        _logger.debug(f'put {iocb!r} prio {iocb.io_priority}')
        # requests should be pending before being queued
        if iocb.io_state != PENDING:
            raise RuntimeError('invalid state transition')
        # add the request to the end of the list of iocb's at same priority
        self.queue.put_nowait(iocb)
        # point the iocb back to this queue
        iocb.io_queue = self

    def get(self):
        """Get a request from a queue."""
        if self.queue.empty():
            # if the queue is empty and we return None
            _logger.debug('    - Queue is empty')
            return None
        # extract the first element
        iocb = self.queue.get_nowait()
        iocb.io_queue = None
        return iocb

    def remove(self, iocb):
        """Remove a control block from the queue, called if the request is canceled/aborted."""
        _logger.debug(f'remove {iocb!r}')
        new_queue = PriorityQueue()
        while not self.queue.empty():
            item = self.queue.get_nowait()
            if item is not iocb:
                new_queue.put_nowait(item)
        self.queue = new_queue

    def abort(self, err):
        """Abort all of the control blocks in the queue."""
        _logger.debug(f'abort {err!r}')
        # send aborts to all of the members
        while not self.queue.empty():
            iocb = self.get()
            iocb.io_queue = None
            iocb.abort(err)
