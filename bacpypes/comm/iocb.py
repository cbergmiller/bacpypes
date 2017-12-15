#!/usr/bin/python

"""
IOCB Module
"""

import logging
import threading

from ..debugging import DebugContents
from ..task import call_later
from .iocb_states import *

_logger = logging.getLogger(__name__)

# globals
local_controllers = {}

# special abort error
TimeoutError = RuntimeError("timeout")

_identNext = 1
_identLock = threading.Lock()


class IOCB(DebugContents):
    """
    IOCB - Input Output Control Block
    """
    _debug_contents = ('args', 'kwargs', 'ioState', 'ioResponse-', 'ioError', 'ioController', 'ioServerRef',
                       'ioControllerRef', 'ioClientID', 'ioClientAddr', 'ioComplete', 'ioCallback+', 'ioQueue',
                       'ioPriority', 'ioTimeout')

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
        self.io_timeout = None

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
        if self.io_timeout:
            _logger.debug("    - cancel timeout")
            self.io_timeout.suspend_task()
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
        _logger.debug(f'set_timeout({self.ioID}) {delay} err={err!r}')
        # if one has already been created, cancel it
        if self.io_timeout:
            self.io_timeout.cancel()
        self.io_timeout = call_later(delay, self.abort, err)

    def __repr__(self):
        xid = id(self)
        if xid < 0:
            xid += (1 << 32)
        sname = self.__module__ + '.' + self.__class__.__name__
        desc = "(%d)" % self.ioID
        return '<' + sname + desc + ' instance at 0x%08x' % (xid,) + '>'


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
