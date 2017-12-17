
import logging
from .iocb_states import *
from .iocb import IOCB

_logger = logging.getLogger(__name__)
__all__ = ['IOController']


class IOController(object):
    """
    An IOController is an API for processing an IOCB.  It has one method
    `process_io()` provided by a derived class which will be called for each IOCB
    that is requested of it.  It calls one of its `complete_io()` or `abort_io()`
    functions as necessary to satisfy the request.

    This class does not restrict a controller from processing more than one
    IOCB simultaneously.
    """
    def __init__(self, name=None):
        """Initialize a controller."""
        _logger.debug('__init__ name=%r', name)
        # save the name
        self.name = name

    def abort(self, err: Exception):
        """
        This method is called to abort all of the IOCBs associated with the controller.
        There is no default implementation of this method.
        :param err: the error to be returned
        """
        pass

    def request_io(self, iocb: IOCB):
        """
        Execute an IO Request.
        This method is called by the application requesting the service of a controller.
        :param iocb: the IOCB to be processed
        """
        _logger.debug('request_io %r', iocb)
        # check that the parameter is an IOCB
        if not isinstance(iocb, IOCB):
            raise TypeError('IOCB expected')
        # bind the iocb to this controller
        iocb.io_controller = self
        try:
            # change the state
            iocb.io_state = PENDING
            # let derived class figure out how to process this
            self._process_io(iocb)
        except Exception as e:
            # if there was an error, abort the request
            self.abort_io(iocb, e)

    def _process_io(self, iocb):
        """
        Figure out how to respond to this request.  This must be provided by the derived class.
        The implementation of `process_io()` should be written using "functional
        programming" principles by not modifying the arguments or keyword arguments
        in the IOCB, and without side effects that would require the application
        using the controller to submit IOCBs in a particular order.  There may be
        occasions following a "remote procedure call" model where the application
        making the request is not in the same process, or even on the same machine,
        as the controller providing the functionality.
        :param iocb: the IOCB to be processed
        """
        raise NotImplementedError('IOController must implement process_io()')

    def active_io(self, iocb: IOCB):
        """
        This method is called by the derived class when it would like to signal
        to other types of applications that the IOCB is being processed.
        :param iocb: the IOCB being processed
        """
        _logger.debug('active_io %r', iocb)
        # requests should be idle or pending before coming active
        if (iocb.io_state != IDLE) and (iocb.io_state != PENDING):
            raise RuntimeError(f'invalid state transition (currently {iocb.io_state})')
        # change the state
        iocb.io_state = ACTIVE

    def complete_io(self, iocb: IOCB, msg):
        """
        This method is called by the derived class when the IO processing is
        complete.  The `msg`, which may be None, is put in the `ioResponse`
        attribute of the IOCB which is then triggered.
        IOController derived classes should call this function rather than
        the `complete()` function of the IOCB.
        :param iocb: the IOCB to be processed
        :param msg: the message to be returned
        """
        _logger.debug('complete_io %r %r', iocb, msg)
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

    def abort_io(self, iocb: IOCB, err: Exception):
        """
        This method is called by the derived class when the IO processing has
        encountered an error.  The `msg` is put in the `ioError`
        attribute of the IOCB which is then triggered.
        IOController derived classes should call this function rather than
        the `abort()` function of the IOCB.
        :param iocb: the IOCB to be processed
        :param msg: the error to be returned
        """
        _logger.debug('abort_io %r %r', iocb, err)
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
