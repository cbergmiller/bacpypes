
import logging
import threading

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
    """
    _debug_contents = ('args', 'kwargs', 'io_state', 'io_response-', 'io_error', 'io_controller', 'ioServerRef',
                       'ioControllerRef', 'ioClientID', 'ioClientAddr', 'io_complete', 'io_callback+', 'io_queue',
                       'io_priority', 'io_timeout')

    def __init__(self, *args, **kwargs):
        # lock the identity sequence number
        with _ident_lock:
            # generate a unique identity for this block
            global _ident_next
            io_id = _ident_next
            _ident_next += 1
        # debugging postponed until ID acquired
        _logger.debug(f'__init__({io_id}) {args!r} {kwargs!r}')
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
        self.io_complete = threading.Event()
        self.io_complete.clear()
        # applications can set a callback functions
        self.io_callback = []
        # request is not currently queued
        self.io_queue = None
        self.io_priority = 0
        # extract the priority if it was given
        if '_priority' in kwargs:
            self.io_priority = kwargs.pop('_priority')
            _logger.debug(f'    - io priority: {self.io_priority!r}')
        # request has no timeout
        self.io_timeout = None

    def add_callback(self, fn, *args, **kwargs):
        """Pass a function to be called when IO is complete."""
        _logger.debug(f'add_callback({self.io_id}) {fn!r} {args!r} {kwargs!r}')
        # store it
        self.io_callback.append((fn, args, kwargs))
        # already complete?
        if self.io_complete.isSet():
            self.trigger()

    def wait(self, *args):
        """Wait for the completion event to be set."""
        _logger.debug(f'wait({self.io_id}) {args!r}')
        # waiting from a non-daemon thread could be trouble
        self.io_complete.wait(*args)

    def trigger(self):
        """Set the completion event and make the callback(s)."""
        _logger.debug(f'trigger({self.io_id})')
        # if it's queued, remove it from its queue
        if self.io_queue:
            _logger.debug('    - dequeue')
            self.io_queue.remove(self)
        # if there's a timer, cancel it
        if self.io_timeout:
            _logger.debug('    - cancel timeout')
            self.io_timeout.cancel()
        # set the completion event
        self.io_complete.set()
        _logger.debug('    - complete event set')
        # make the callback(s)
        for fn, args, kwargs in self.io_callback:
            _logger.debug(f'    - callback fn: {fn!r} {args!r} {kwargs!r}')
            fn(self, *args, **kwargs)

    def complete(self, msg):
        """
        Called to complete a transaction, usually when ProcessIO has
        shipped the IOCB off to some other thread or function.
        """
        _logger.debug(f'complete({self.io_id}) {msg!r}')
        if self.io_controller:
            # pass to controller
            self.io_controller.complete_io(self, msg)
        else:
            # just fill in the data
            self.io_state = COMPLETED
            self.io_response = msg
            self.trigger()

    def abort(self, err):
        """Called by a client to abort a transaction."""
        _logger.debug(f'abort({self.io_id}) {err!r}')
        if self.io_controller:
            # pass to controller
            self.io_controller.abort_io(self, err)
        elif self.io_state < COMPLETED:
            # just fill in the data
            self.io_state = ABORTED
            self.io_error = err
            self.trigger()

    def set_timeout(self, delay, err=TimeoutError):
        """Called to set a transaction timer."""
        _logger.debug(f'set_timeout({self.io_id}) {delay} err={err!r}')
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

