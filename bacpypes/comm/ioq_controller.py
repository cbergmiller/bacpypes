
import time
import logging
from ..task import call_later
from ..core import deferred
from .iocb_states import *
from .io_controller import IOController
from .io_queue import IOQueue

_logger = logging.getLogger(__name__)
__all__ = ['IOQController']

#  IOQController States
CTRL_IDLE = 0  # nothing happening
CTRL_ACTIVE = 1  # working on an iocb
CTRL_WAITING = 1  # waiting between iocb requests (throttled)

# current time formatting (short version)
_strftime = lambda: "%011.6f" % (time.time() % 3600,)


class IOQController(IOController):
    wait_time = 0.0

    def __init__(self, name=None):
        """Initialize a queue controller."""
        _logger.debug("__init__ name=%r", name)
        IOController.__init__(self, name)
        # start idle
        self.state = CTRL_IDLE
        _logger.debug("%s %s %s" % (_strftime(), self.name, "idle"))
        # no active iocb
        self.active_iocb = None
        # create an IOQueue for iocb's requested when not idle
        self.ioQueue = IOQueue(str(name) + " queue")

    def abort(self, err):
        """Abort all pending requests."""
        _logger.debug("abort %r", err)
        if self.state == CTRL_IDLE:
            _logger.debug("    - idle")
            return
        while True:
            iocb = self.ioQueue.get(block=0)
            if not iocb:
                break
            _logger.debug("    - iocb: %r", iocb)
            # change the state
            iocb.ioState = ABORTED
            iocb.ioError = err
            # notify the client
            iocb.trigger()
        if self.state != CTRL_IDLE:
            _logger.debug("    - busy after aborts")

    def request_io(self, iocb):
        """Called by a client to start processing a request."""
        _logger.debug("request_io %r", iocb)
        # bind the iocb to this controller
        iocb.ioController = self
        # if we're busy, queue it
        if self.state != CTRL_IDLE:
            _logger.debug("    - busy, request queued, active_iocb: %r", self.active_iocb)
            iocb.ioState = PENDING
            self.ioQueue.put(iocb)
            return
        try:
            # hopefully there won't be an error
            err = None
            # let derived class figure out how to process this
            self.process_io(iocb)
        except Exception as e:
            _logger.debug("    - process_io() exception: %r", e)
        # if there was an error, abort the request
        if err:
            _logger.debug("    - aborting")
            self.abort_io(iocb, e)

    def process_io(self, iocb):
        """Figure out how to respond to this request.  This must be
        provided by the derived class."""
        raise NotImplementedError("IOController must implement process_io()")

    def active_io(self, iocb):
        """Called by a handler to notify the controller that a request is
        being processed."""
        _logger.debug("active_io %r", iocb)
        # base class work first, setting iocb state and timer data
        IOController.active_io(self, iocb)
        # change our state
        self.state = CTRL_ACTIVE
        _logger.debug("%s %s %s" % (_strftime(), self.name, "active"))
        # keep track of the iocb
        self.active_iocb = iocb

    def complete_io(self, iocb, msg):
        """Called by a handler to return data to the client."""
        _logger.debug("complete_io %r %r", iocb, msg)
        # check to see if it is completing the active one
        if iocb is not self.active_iocb:
            raise RuntimeError("not the current iocb")
        # normal completion
        IOController.complete_io(self, iocb, msg)
        # no longer an active iocb
        self.active_iocb = None
        # check to see if we should wait a bit
        if self.wait_time:
            # change our state
            self.state = CTRL_WAITING
            _logger.debug("%s %s %s" % (_strftime(), self.name, "waiting"))
            # schedule a call in the future
            call_later(self.wait_time, IOQController._wait_trigger, self)
        else:
            # change our state
            self.state = CTRL_IDLE
            _logger.debug("%s %s %s" % (_strftime(), self.name, "idle"))
            # look for more to do
            deferred(IOQController._trigger, self)

    def abort_io(self, iocb, err):
        """Called by a handler or a client to abort a transaction."""
        _logger.debug("abort_io %r %r", iocb, err)
        # normal abort
        IOController.abort_io(self, iocb, err)
        # check to see if it is completing the active one
        if iocb is not self.active_iocb:
            _logger.debug("    - not current iocb")
            return
        # no longer an active iocb
        self.active_iocb = None
        # change our state
        self.state = CTRL_IDLE
        _logger.debug("%s %s %s" % (_strftime(), self.name, "idle"))
        # look for more to do
        deferred(IOQController._trigger, self)

    def _trigger(self):
        """Called to launch the next request in the queue."""
        _logger.debug("_trigger")
        # if we are busy, do nothing
        if self.state != CTRL_IDLE:
            _logger.debug("    - not idle")
            return
        # if there is nothing to do, return
        if not self.ioQueue.queue:
            _logger.debug("    - empty queue")
            return
        # get the next iocb
        iocb = self.ioQueue.get()
        try:
            # hopefully there won't be an error
            err = None
            # let derived class figure out how to process this
            self.process_io(iocb)
        except Exception as e:
            # if there was an error, abort the request
            self.abort_io(iocb, e)
        # if we're idle, call again
        if self.state == CTRL_IDLE:
            deferred(IOQController._trigger, self)

    def _wait_trigger(self):
        """Called to launch the next request in the queue."""
        _logger.debug("_wait_trigger")
        # make sure we are waiting
        if self.state != CTRL_WAITING:
            raise RuntimeError("not waiting")
        # change our state
        self.state = CTRL_IDLE
        _logger.debug("%s %s %s" % (_strftime(), self.name, "idle"))
        # look for more to do
        IOQController._trigger(self)
