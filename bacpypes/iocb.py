#!/usr/bin/python

"""
IOCB Module
"""

import sys
import logging
from time import time as _time

import threading
from bisect import bisect_left

from .debugging import bacpypes_debugging, ModuleLogger, DebugContents

from .core import deferred
from .task import FunctionTask
from .comm import Client


_logger = logging.getLogger(__name__)

# globals
local_controllers = {}

#
#   IOCB States
#

IDLE = 0        # has not been submitted
PENDING = 1     # queued, waiting for processing
ACTIVE = 2      # being processed
COMPLETED = 3   # finished
ABORTED = 4     # finished in a bad way

_stateNames = {
    0: 'IDLE',
    1: 'PENDING',
    2: 'ACTIVE',
    3: 'COMPLETED',
    4: 'ABORTED',
    }

#
#   IOQController States
#

CTRL_IDLE = 0       # nothing happening
CTRL_ACTIVE = 1     # working on an iocb
CTRL_WAITING = 1    # waiting between iocb requests (throttled)

_ctrlStateNames = {
    0: 'IDLE',
    1: 'ACTIVE',
    2: 'WAITING',
    }

# special abort error
TimeoutError = RuntimeError("timeout")

# current time formatting (short version)
_strftime = lambda: "%011.6f" % (_time() % 3600,)


_identNext = 1
_identLock = threading.Lock()


class IOCB(DebugContents):
    """
    IOCB - Input Output Control Block
    """
    def __init__(self, *args, **kwargs):
        global _identNext
        # lock the identity sequence number
        _identLock.acquire()
        # generate a unique identity for this block
        ioID = _identNext
        _identNext += 1
        # release the lock
        _identLock.release()
        # debugging postponed until ID acquired
        _logger.debug("__init__(%d) %r %r", ioID, args, kwargs)
        # save the ID
        self.ioID = ioID
        # save the request parameters
        self.args = args
        self.kwargs = kwargs
        # start with an idle request
        self.ioState = IDLE
        self.ioResponse = None
        self.ioError = None
        # blocks are bound to a controller
        self.ioController = None
        # each block gets a completion event
        self.ioComplete = threading.Event()
        self.ioComplete.clear()
        # applications can set a callback functions
        self.ioCallback = []
        # request is not currently queued
        self.ioQueue = None
        # extract the priority if it was given
        self.ioPriority = kwargs.get('_priority', 0)
        if '_priority' in kwargs:
            _logger.debug("    - ioPriority: %r", self.ioPriority)
            del kwargs['_priority']
        # request has no timeout
        self.ioTimeout = None

    def add_callback(self, fn, *args, **kwargs):
        """Pass a function to be called when IO is complete."""
        _logger.debug("add_callback(%d) %r %r %r", self.ioID, fn, args, kwargs)
        # store it
        self.ioCallback.append((fn, args, kwargs))
        # already complete?
        if self.ioComplete.isSet():
            self.trigger()

    def wait(self, *args):
        """Wait for the completion event to be set."""
        _logger.debug("wait(%d) %r", self.ioID, args)
        # waiting from a non-daemon thread could be trouble
        self.ioComplete.wait(*args)

    def trigger(self):
        """Set the completion event and make the callback(s)."""
        _logger.debug("trigger(%d)", self.ioID)
        # if it's queued, remove it from its queue
        if self.ioQueue:
            _logger.debug("    - dequeue")
            self.ioQueue.remove(self)
        # if there's a timer, cancel it
        if self.ioTimeout:
            _logger.debug("    - cancel timeout")
            self.ioTimeout.suspend_task()
        # set the completion event
        self.ioComplete.set()
        _logger.debug("    - complete event set")
        # make the callback(s)
        for fn, args, kwargs in self.ioCallback:
            _logger.debug("    - callback fn: %r %r %r", fn, args, kwargs)
            fn(self, *args, **kwargs)

    def complete(self, msg):
        """Called to complete a transaction, usually when ProcessIO has
        shipped the IOCB off to some other thread or function."""
        _logger.debug("complete(%d) %r", self.ioID, msg)
        if self.ioController:
            # pass to controller
            self.ioController.complete_io(self, msg)
        else:
            # just fill in the data
            self.ioState = COMPLETED
            self.ioResponse = msg
            self.trigger()

    def abort(self, err):
        """Called by a client to abort a transaction."""
        _logger.debug("abort(%d) %r", self.ioID, err)
        if self.ioController:
            # pass to controller
            self.ioController.abort_io(self, err)
        elif self.ioState < COMPLETED:
            # just fill in the data
            self.ioState = ABORTED
            self.ioError = err
            self.trigger()

    def set_timeout(self, delay, err=TimeoutError):
        """Called to set a transaction timer."""
        _logger.debug("set_timeout(%d) %r err=%r", self.ioID, delay, err)
        # if one has already been created, cancel it
        if self.ioTimeout:
            self.ioTimeout.suspend_task()
        else:
            self.ioTimeout = FunctionTask(self.abort, err)
        # (re)schedule it
        self.ioTimeout.install_task(delta=delay)

    def __repr__(self):
        xid = id(self)
        if xid < 0:
            xid += (1 << 32)
        sname = self.__module__ + '.' + self.__class__.__name__
        desc = "(%d)" % (self.ioID)
        return '<' + sname + desc + ' instance at 0x%08x' % (xid,) + '>'


class IOChainMixIn(DebugContents):

    _debug_contents = ( 'ioChain++', )

    def __init__(self, iocb):
        _logger.debug("__init__ %r", iocb)
        # save a refence back to the iocb
        self.ioChain = iocb
        # set the callback to follow the chain
        self.add_callback(self.chain_callback)
        # if we're not chained, there's no notification to do
        if not self.ioChain:
            return
        # this object becomes its controller
        iocb.ioController = self
        # consider the parent active
        iocb.ioState = ACTIVE
        try:
            _logger.debug("    - encoding")
            # let the derived class set the args and kwargs
            self.encode()
            _logger.debug("    - encode complete")
        except Exception:
            # extract the error and abort the request
            err = sys.exc_info()[1]
            _logger.exception("    - encoding exception: %r", err)
            iocb.abort(err)

    def chain_callback(self, iocb):
        """Callback when this iocb completes."""
        _logger.debug("chain_callback %r", iocb)
        # if we're not chained, there's no notification to do
        if not self.ioChain:
            return
        # refer to the chained iocb
        iocb = self.ioChain
        try:
            _logger.debug("    - decoding")
            # let the derived class transform the data
            self.decode()
            _logger.debug("    - decode complete")
        except Exception:
            # extract the error and abort
            err = sys.exc_info()[1]
            _logger.exception("    - decoding exception: %r", err)
            iocb.ioState = ABORTED
            iocb.ioError = err
        # break the references
        self.ioChain = None
        iocb.ioController = None
        # notify the client
        iocb.trigger()

    def abort_io(self, iocb, err):
        """Forward the abort downstream."""
        _logger.debug("abort_io %r %r", iocb, err)
        # make sure we're being notified of an abort request from
        # the iocb we are chained from
        if iocb is not self.ioChain:
            raise RuntimeError("broken chain")
        # call my own Abort(), which may forward it to a controller or
        # be overridden by IOGroup
        self.abort(err)

    def encode(self):
        """Hook to transform the request, called when this IOCB is
        chained."""
        _logger.debug("encode")
        # by default do nothing, the arguments have already been supplied

    def decode(self):
        """Hook to transform the response, called when this IOCB is
        completed."""
        _logger.debug("decode")
        # refer to the chained iocb
        iocb = self.ioChain
        # if this has completed successfully, pass it up
        if self.ioState == COMPLETED:
            _logger.debug("    - completed: %r", self.ioResponse)
            # change the state and transform the content
            iocb.ioState = COMPLETED
            iocb.ioResponse = self.ioResponse
        # if this aborted, pass that up too
        elif self.ioState == ABORTED:
            _logger.debug("    - aborted: %r", self.ioError)
            # change the state
            iocb.ioState = ABORTED
            iocb.ioError = self.ioError
        else:
            raise RuntimeError("invalid state: %d" % (self.ioState,))


class IOChain(IOCB, IOChainMixIn):

    def __init__(self, chain, *args, **kwargs):
        """Initialize a chained control block."""
        _logger.debug("__init__ %r %r %r", chain, args, kwargs)
        # initialize IOCB part to pick up the ioID
        IOCB.__init__(self, *args, **kwargs)
        IOChainMixIn.__init__(self, chain)


class IOGroup(IOCB, DebugContents):

    _debug_contents = ('ioMembers',)

    def __init__(self):
        """Initialize a group."""
        _logger.debug("__init__")
        IOCB.__init__(self)
        # start with an empty list of members
        self.ioMembers = []
        # start out being done.  When an IOCB is added to the
        # group that is not already completed, this state will
        # change to PENDING.
        self.ioState = COMPLETED
        self.ioComplete.set()

    def add(self, iocb):
        """Add an IOCB to the group, you can also add other groups."""
        _logger.debug("add %r", iocb)
        # add this to our members
        self.ioMembers.append(iocb)
        # assume all of our members have not completed yet
        self.ioState = PENDING
        self.ioComplete.clear()
        # when this completes, call back to the group.  If this
        # has already completed, it will trigger
        iocb.add_callback(self.group_callback)

    def group_callback(self, iocb):
        """Callback when a child iocb completes."""
        _logger.debug("group_callback %r", iocb)
        # check all the members
        for iocb in self.ioMembers:
            if not iocb.ioComplete.isSet():
                _logger.debug("    - waiting for child: %r", iocb)
                break
        else:
            _logger.debug("    - all children complete")
            # everything complete
            self.ioState = COMPLETED
            self.trigger()

    def abort(self, err):
        """Called by a client to abort all of the member transactions.
        When the last pending member is aborted the group callback
        function will be called."""
        _logger.debug("abort %r", err)
        # change the state to reflect that it was killed
        self.ioState = ABORTED
        self.ioError = err
        # abort all the members
        for iocb in self.ioMembers:
            iocb.abort(err)

        # notify the client
        self.trigger()


class IOQueue:

    def __init__(self, name=None):
        _logger.debug("__init__ %r", name)
        self.notempty = threading.Event()
        self.notempty.clear()
        self.queue = []

    def put(self, iocb):
        """Add an IOCB to a queue.  This is usually called by the function
        that filters requests and passes them out to the correct processing
        thread."""
        _logger.debug("put %r", iocb)
        # requests should be pending before being queued
        if iocb.ioState != PENDING:
            raise RuntimeError("invalid state transition")
        # save that it might have been empty
        wasempty = not self.notempty.isSet()
        # add the request to the end of the list of iocb's at same priority
        priority = iocb.ioPriority
        item = (priority, iocb)
        self.queue.insert(bisect_left(self.queue, (priority+1,)), item)
        # point the iocb back to this queue
        iocb.ioQueue = self
        # set the event, queue is no longer empty
        self.notempty.set()
        return wasempty

    def get(self, block=1, delay=None):
        """Get a request from a queue, optionally block until a request
        is available."""
        _logger.debug("get block=%r delay=%r", block, delay)
        # if the queue is empty and we do not block return None
        if not block and not self.notempty.isSet():
            _logger.debug("    - not blocking and empty")
            return None
        # wait for something to be in the queue
        if delay:
            self.notempty.wait(delay)
            if not self.notempty.isSet():
                return None
        else:
            self.notempty.wait()
        # extract the first element
        priority, iocb = self.queue[0]
        del self.queue[0]
        iocb.ioQueue = None
        # if the queue is empty, clear the event
        qlen = len(self.queue)
        if not qlen:
            self.notempty.clear()
        # return the request
        return iocb

    def remove(self, iocb):
        """Remove a control block from the queue, called if the request
        is canceled/aborted."""
        _logger.debug("remove %r", iocb)
        # remove the request from the queue
        for i, item in enumerate(self.queue):
            if iocb is item[1]:
                _logger.debug("    - found at %d", i)
                del self.queue[i]
                # if the queue is empty, clear the event
                qlen = len(self.queue)
                if not qlen:
                    self.notempty.clear()
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
            self.notempty.clear()
        except ValueError:
            pass


class IOController(object):

    def __init__(self, name=None):
        """Initialize a controller."""
        _logger.debug("__init__ name=%r", name)
        # save the name
        self.name = name

    def abort(self, err):
        """Abort all requests, no default implementation."""
        pass

    def request_io(self, iocb):
        """Called by a client to start processing a request."""
        _logger.debug("request_io %r", iocb)
        # check that the parameter is an IOCB
        if not isinstance(iocb, IOCB):
            raise TypeError("IOCB expected")
        # bind the iocb to this controller
        iocb.ioController = self
        try:
            # hopefully there won't be an error
            err = None
            # change the state
            iocb.ioState = PENDING
            # let derived class figure out how to process this
            self.process_io(iocb)
        except Exception:
            # extract the error
            err = sys.exc_info()[1]
        # if there was an error, abort the request
        if err:
            self.abort_io(iocb, err)

    def process_io(self, iocb):
        """Figure out how to respond to this request.  This must be
        provided by the derived class."""
        raise NotImplementedError("IOController must implement process_io()")

    def active_io(self, iocb):
        """Called by a handler to notify the controller that a request is
        being processed."""
        _logger.debug("active_io %r", iocb)
        # requests should be idle or pending before coming active
        if (iocb.ioState != IDLE) and (iocb.ioState != PENDING):
            raise RuntimeError("invalid state transition (currently %d)" % (iocb.ioState,))
        # change the state
        iocb.ioState = ACTIVE

    def complete_io(self, iocb, msg):
        """Called by a handler to return data to the client."""
        _logger.debug("complete_io %r %r", iocb, msg)
        # if it completed, leave it alone
        if iocb.ioState == COMPLETED:
            pass
        # if it already aborted, leave it alone
        elif iocb.ioState == ABORTED:
            pass
        else:
            # change the state
            iocb.ioState = COMPLETED
            iocb.ioResponse = msg
            # notify the client
            iocb.trigger()

    def abort_io(self, iocb, err):
        """Called by a handler or a client to abort a transaction."""
        _logger.debug("abort_io %r %r", iocb, err)
        # if it completed, leave it alone
        if iocb.ioState == COMPLETED:
            pass
        # if it already aborted, leave it alone
        elif iocb.ioState == ABORTED:
            pass
        else:
            # change the state
            iocb.ioState = ABORTED
            iocb.ioError = err

            # notify the client
            iocb.trigger()


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
        except Exception:
            # extract the error
            err = sys.exc_info()[1]
            _logger.debug("    - process_io() exception: %r", err)
        # if there was an error, abort the request
        if err:
            _logger.debug("    - aborting")
            self.abort_io(iocb, err)

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
            task = FunctionTask(IOQController._wait_trigger, self)
            task.install_task(delta=self.wait_time)
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
        except Exception:
            # extract the error
            err = sys.exc_info()[1]
        # if there was an error, abort the request
        if err:
            self.abort_io(iocb, err)
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


class ClientController(Client, IOQController):

    def __init__(self):
        _logger.debug("__init__")
        Client.__init__(self)
        IOQController.__init__(self)

    def process_io(self, iocb):
        _logger.debug("process_io %r", iocb)
        # this is now an active request
        self.active_io(iocb)
        # send the PDU downstream
        self.request(iocb.args[0])

    def confirmation(self, pdu):
        _logger.debug("confirmation %r", pdu)
        # make sure it has an active iocb
        if not self.active_iocb:
            ClientController._debug("no active request")
            return
        # look for exceptions
        if isinstance(pdu, Exception):
            self.abort_io(self.active_iocb, pdu)
        else:
            self.complete_io(self.active_iocb, pdu)


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
        if not queue.ioQueue.queue and not queue.active_iocb:
            _logger.debug("    - queue is empty")
            del self.queues[source_address]


def register_controller(controller):
    _logger.debug("register_controller %r", controller)
    global local_controllers
    # skip those that shall not be named
    if not controller.name:
        return
    # make sure there isn't one already
    if controller.name in local_controllers:
        raise RuntimeError("already a local controller named %r" % (controller.name,))
    local_controllers[controller.name] = controller


def abort(err):
    """Abort everything, everywhere."""
    _logger.debug("abort %r", err)
    global local_controllers
    # tell all the local controllers to abort
    for controller in local_controllers.values():
        controller.abort(err)
