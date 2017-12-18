
"""
IO Control Block
================

The IO Control Block (IOCB) is a data structure that is used to store parameters
for some kind of processing and then used to retrieve the results of that
processing at a later time.  An IO Controller (IOController) is the executor
of that processing.

They are modeled after the VAX/VMS IO subsystem API in which a single function
could take a wide variety of combinations of parameters and the application
did not necessarily wait for the operation to complete, but could be notified
when it was by an event flag or semaphore.  It could also provide a callback
function to be called when processing was complete.

For example, given a simple function call::

    result = some_function(arg1, arg2, kwarg1=1)

The IOCB would contain the arguments and keyword arguments, the some_function()
would be the controller, and the result would alo be stored in the IOCB when
the function is complete.

If the IOController encountered an error during processing, some value specifying
the error is also stored in the IOCB.

Classes
-------

There are two fundamental classes in this module, the :class:`IOCB` for bundling
request parameters together and processing the result, and :class:`IOController`
for executing requests.

The :class:`IOQueue` is an object that manages a queue of IOCB requests when
some functionality needs to be processed one at a time, and an :class:`IOQController`
which has the same signature as an IOController but takes advantage of a queue.

The :class:`IOGroup` is used to bundle a collection of requests together that
may be processed by separate controllers at different times but has `wait()`
and `add_callback()` functions and can be otherwise treated as an IOCB.
"""

import logging
import threading
import asyncio

from ..debugging import DebugContents
from ..task import call_later
from .iocb_states import *

_logger = logging.getLogger(__name__)
_ident_next = 1
_ident_lock = threading.Lock()
__all__ = ['IOCB']


class IOCB(DebugContents):
    """
    IOCB - Input Output Control Block

    The IOCB contains a unique identifier, references to the arguments and
    keyword arguments used when it was constructed, and placeholders for
    processing results or errors.
    Every IOCB has a unique identifier that persists for the lifetime of
    the block.  Similar to the Invoke ID for confirmed services, it can be used
    to synchronize communications and related functions.
    The default identifier value is a thread safe monotonically increasing
    value.
    The ioState of an IOCB is the state of processing for the block.
        * *idle* - an IOCB is idle when it is first constructed and before it has been given to a controller.
        * *pending* - the IOCB has been given to a controller but the processing of the request has not started.
        * *active* - the IOCB is being processed by the controller.
        * *completed* - the processing of the IOCB has completed and the positive results have been stored in `ioResponse`.
        * *aborted* - the processing of the IOCB has encountered an error of some kind and the error condition has been stored in `ioError`.
    """
    _debug_contents = ('args', 'kwargs', 'io_state', 'io_response-', 'io_error', 'io_controller', 'io_complete',
                       'io_callback+', 'io_priority', 'io_timeout')

    def __init__(self, *args, **kwargs):
        # lock the identity sequence number
        with _ident_lock:
            # generate a unique identity for this block
            global _ident_next
            io_id = _ident_next
            _ident_next += 1
        # debugging postponed until ID acquired
        _logger.debug('__init__(%d) %r %r', io_id, args, kwargs)
        # save the ID
        self.io_id = io_id
        # save the request parameters
        self.args = args
        self.kwargs = kwargs
        # start with an idle request
        self.io_state = IDLE
        self.io_response = None
        self.io_error = None
        # blocks are bound to a controller
        self.io_controller = None
        # each block gets a completion event
        self.io_complete = asyncio.Event()
        # applications can set a callback functions
        self.io_callback = []
        self.io_priority = 0
        # extract the priority if it was given
        if '_priority' in kwargs:
            self.io_priority = kwargs.pop('_priority')
            _logger.debug('    - io priority: %s', self.io_priority)
        # request has no timeout
        self.io_timeout = None

    def add_callback(self, fn, *args, **kwargs):
        """
        Add the function `fn` to a list of functions to call when the IOCB is
        triggered because it is complete or aborted.  When the function is
        called the first parameter will be the IOCB that was triggered.

        An IOCB can have any number of callback functions added to it and they
        will be called in the order they were added to the IOCB.

        If the IOCB is has already been triggered then the callback function
        will be called immediately.  Callback functions are typically added
        to an IOCB before it is given to a controller.
        """
        _logger.debug('add_callback(%d) %r %r %r', self.io_id, fn, args, kwargs)
        # store it
        self.io_callback.append((fn, args, kwargs))
        # already complete?
        if self.io_complete.is_set():
            self.trigger()

    async def wait(self):
        """
        Block until the IO operation is complete and the positive or negative
        result has been placed in the ICOB.
        """
        _logger.debug('wait(%d)', self.io_id)
        await self.io_complete.wait()

    def trigger(self):
        """
        This method is called by complete() or abort() after the positive or
        negative result has been stored in the IOCB.
        """
        _logger.debug('trigger(%d)', self.io_id)
        # Set the completion event and make the callback(s).
        # if there's a timer, cancel it
        if self.io_timeout:
            _logger.debug('    - cancel timeout')
            self.io_timeout.cancel()
        # set the completion event
        self.io_complete.set()
        _logger.debug('    - complete event set')
        # make the callback(s)
        for fn, args, kwargs in self.io_callback:
            _logger.debug('    - callback fn: %r %r %r', fn, args, kwargs)
            fn(self, *args, **kwargs)

    def complete(self, msg):
        """
        Called to complete a transaction, usually when ProcessIO has
        shipped the IOCB off to some other thread or function.
        """
        _logger.debug('complete(%d) %r', self.io_id, msg)
        if self.io_controller:
            # pass to controller
            self.io_controller.complete_io(self, msg)
        else:
            # just fill in the data
            self.io_state = COMPLETED
            self.io_response = msg
            self.trigger()

    def abort(self, err):
        """
        Called by a client to abort a transaction.
        :param msg: negative results of request
        """
        _logger.debug('abort(%d) %r', self.io_id, err)
        if self.io_controller:
            # pass to controller
            self.io_controller.abort_io(self, err)
        elif self.io_state < COMPLETED:
            # just fill in the data
            self.io_state = ABORTED
            self.io_error = err
            self.trigger()

    def set_timeout(self, delay, err=TimeoutError):
        """
        Set a time limit on the amount of time an IOCB can take to be completed,
        and if the time is exceeded then the IOCB is aborted.
        :param seconds delay: the time limit for processing the IOCB
        :param err: the error to use when the IOCB is aborted
        """
        _logger.debug('set_timeout(%d) %s err=%r', self.io_id, delay, err)
        # if one has already been created, cancel it
        if self.io_timeout:
            self.io_timeout.cancel()
        self.io_timeout = call_later(delay, self.abort, err)

    def __repr__(self):
        return f'<{self.__module__}.{self.__class__.__name__} instance ({self.io_id})>'

    def __lt__(self, other):
        """Instances have to be comparable with < to work with Priority Queue."""
        assert isinstance(other, IOCB)
        # ToDo: check order of priority
        if self.io_priority != other.io_priority:
            return self.io_priority < other.io_priority
        else:
            return self.io_id < other.io_id

