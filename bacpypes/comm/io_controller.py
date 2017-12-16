
import logging
from .iocb_states import *
from .iocb import IOCB

_logger = logging.getLogger(__name__)
__all__ = ['IOController']


class IOController(object):

    def __init__(self, name=None):
        """Initialize a controller."""
        _logger.debug(f'__init__ name={name!r}')
        # save the name
        self.name = name

    def abort(self, err):
        """Abort all requests, no default implementation."""
        pass

    def request_io(self, iocb: IOCB):
        """Called by a client to start processing a request."""
        _logger.debug(f'request_io {iocb!r}')
        # check that the parameter is an IOCB
        if not isinstance(iocb, IOCB):
            raise TypeError('IOCB expected')
        # bind the iocb to this controller
        iocb.io_controller = self
        try:
            # change the state
            iocb.io_state = PENDING
            # let derived class figure out how to process this
            self.process_io(iocb)
        except Exception as e:
            # if there was an error, abort the request
            self.abort_io(iocb, e)

    def process_io(self, iocb):
        """Figure out how to respond to this request.  This must be provided by the derived class."""
        raise NotImplementedError('IOController must implement process_io()')

    def active_io(self, iocb):
        """Called by a handler to notify the controller that a request is being processed."""
        _logger.debug('active_io {iocb!r}')
        # requests should be idle or pending before coming active
        if (iocb.io_state != IDLE) and (iocb.io_state != PENDING):
            raise RuntimeError("invalid state transition (currently %d)" % (iocb.io_state,))
        # change the state
        iocb.io_state = ACTIVE

    def complete_io(self, iocb, msg):
        """Called by a handler to return data to the client."""
        _logger.debug(f'complete_io {iocb!r} {msg!r}')
        if iocb.io_state == COMPLETED:
            # if it completed, leave it alone
            pass
        elif iocb.io_state == ABORTED:
            # if it already aborted, leave it alone
            pass
        else:
            # change the state
            iocb.io_state = COMPLETED
            iocb.io_response = msg
            # notify the client
            iocb.trigger()

    def abort_io(self, iocb, err):
        """Called by a handler or a client to abort a transaction."""
        _logger.debug(f'abort_io {iocb!r} {err!r}')
        if iocb.io_state == COMPLETED:
            # if it completed, leave it alone
            pass
        elif iocb.io_state == ABORTED:
            # if it already aborted, leave it alone
            pass
        else:
            # change the state
            iocb.io_state = ABORTED
            iocb.io_error = err
            # notify the client
            iocb.trigger()
