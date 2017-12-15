
import logging
import threading
from bisect import bisect_left
from .iocb_states import *

_logger = logging.getLogger(__name__)
__all__ = ['IOQueue']


class IOQueue:

    def __init__(self, name=None):
        _logger.debug("__init__ %r", name)
        self.not_empty = threading.Event()
        self.not_empty.clear()
        self.queue = []

    def put(self, iocb):
        """
        Add an IOCB to a queue. This is usually called by the function that filters
        requests and passes them out to the correct processing thread.
        """
        _logger.debug("put %r", iocb)
        # requests should be pending before being queued
        if iocb.ioState != PENDING:
            raise RuntimeError("invalid state transition")
        # save that it might have been empty
        was_empty = not self.not_empty.isSet()
        # add the request to the end of the list of iocb's at same priority
        priority = iocb.ioPriority
        item = (priority, iocb)
        self.queue.insert(bisect_left(self.queue, (priority + 1,)), item)
        # point the iocb back to this queue
        iocb.ioQueue = self
        # set the event, queue is no longer empty
        self.not_empty.set()
        return was_empty

    def get(self, block=1, delay=None):
        """Get a request from a queue, optionally block until a request is available."""
        _logger.debug("get block=%r delay=%r", block, delay)
        # if the queue is empty and we do not block return None
        if not block and not self.not_empty.isSet():
            _logger.debug("    - not blocking and empty")
            return None
        # wait for something to be in the queue
        if delay:
            self.not_empty.wait(delay)
            if not self.not_empty.isSet():
                return None
        else:
            self.not_empty.wait()
        # extract the first element
        priority, iocb = self.queue[0]
        del self.queue[0]
        iocb.ioQueue = None
        # if the queue is empty, clear the event
        qlen = len(self.queue)
        if not qlen:
            self.not_empty.clear()
        # return the request
        return iocb

    def remove(self, iocb):
        """Remove a control block from the queue, called if the request is canceled/aborted."""
        _logger.debug("remove %r", iocb)
        # remove the request from the queue
        for i, item in enumerate(self.queue):
            if iocb is item[1]:
                _logger.debug("    - found at %d", i)
                del self.queue[i]
                # if the queue is empty, clear the event
                qlen = len(self.queue)
                if not qlen:
                    self.not_empty.clear()
                # record the new length
                # self.queuesize.Record( qlen, _time() )
                break
        else:
            _logger.debug("    - not found")

    def abort(self, err):
        """Abort all of the control blocks in the queue."""
        _logger.debug("abort %r", err)
        # send aborts to all of the members
        try:
            for iocb in self.queue:
                iocb.ioQueue = None
                iocb.abort(err)
            # flush the queue
            self.queue = []
            # the queue is now empty, clear the event
            self.not_empty.clear()
        except ValueError:
            pass