
import logging
from .iocb_states import *
from .iocb import IOCB
from asyncio import PriorityQueue

_logger = logging.getLogger(__name__)
__all__ = ['IOQueue']


class IOQueue:
    """
    Prioritized Queue for IOCB instances.
    """
    def __init__(self):
        self.queue = PriorityQueue()

    @property
    def empty(self):
        return self.queue.empty()

    def put(self, iocb: IOCB):
        """
        Add an IOCB to a queue. This is usually called by the function that filters
        requests and passes them out to the correct processing thread.
        """
        # requests should be pending before being queued
        if iocb.io_state != PENDING:
            raise RuntimeError('invalid state transition')
        # add the request to the end of the list of iocb's at same priority
        self.queue.put_nowait(iocb)

    def get(self) -> IOCB:
        """Get a request from a queue."""
        return self.queue.get_nowait()
