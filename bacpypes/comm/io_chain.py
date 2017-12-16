import logging

from ..debugging import DebugContents
from .iocb import IOCB
from .iocb_states import *

_logger = logging.getLogger(__name__)
__all__ = ['IOChain']


class IOChain(IOCB, DebugContents):
    """
    An IOChain is a class that is an IOCB that includes the IOChain API.
    Chains are used by controllers when they need the services of some other
    controller and results need to be processed further.

    Controllers that operate this way are similar to an adapter, they take
    arguments in one form, encode them in some way in an IOCB, pass it to the
    other controller, then decode the results.
    """
    _debug_contents = ('ioChain++',)

    def __init__(self, chain: IOCB, *args, **kwargs):
        """Initialize a chained control block."""
        _logger.debug("__init__ %r %r %r", chain, args, kwargs)
        # initialize IOCB part to pick up the ioID
        IOCB.__init__(self, *args, **kwargs)
        # save a refence back to the iocb
        self.ioChain = chain
        # set the callback to follow the chain
        self.add_callback(self.chain_callback)
        # if we're not chained, there's no notification to do
        if not self.ioChain:
            return
        # this object becomes its controller
        chain.io_controller = self
        # consider the parent active
        chain.io_state = ACTIVE
        try:
            _logger.debug("    - encoding")
            # let the derived class set the args and kwargs
            self.encode()
            _logger.debug("    - encode complete")
        except Exception as e:
            # extract the error and abort the request
            _logger.exception("    - encoding exception: %r", e)
            chain.abort(e)

    def chain_callback(self, iocb: IOCB):
        """
        When a chained IOCB has completed, the results are translated or
        decoded for the next higher level of the application.  The `iocb`
        parameter is redundant because the IOCB becomes its own controller,
        but the callback API requires the parameter.
        :param iocb: the IOCB that has completed, which is itself
        """
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
        except Exception as e:
            # extract the error and abort
            _logger.exception("    - decoding exception: %r", e)
            iocb.io_state = ABORTED
            iocb.io_error = e
        # break the references
        self.ioChain = None
        iocb.io_controller = None
        # notify the client
        iocb.trigger()

    def abort_io(self, iocb: IOCB, err: Exception):
        """
        Call this method to abort the IOCB, which will in turn cascade the
        abort operation to the chained IOCBs.  This has the same function
        signature that is used by an IOController because this instance
        becomes its own controller.
        :param iocb: the IOCB that is being aborted
        :param err: the error to be used as the abort reason
        """
        _logger.debug("abort_io %r %r", iocb, err)
        # make sure we're being notified of an abort request from
        # the iocb we are chained from
        if iocb is not self.ioChain:
            raise RuntimeError("broken chain")
        # call my own Abort(), which may forward it to a controller or
        # be overridden by IOGroup
        self.abort(err)

    def encode(self):
        """
        This method is called to transform the arguments and keyword arguments
        into something suitable for the other controller.  It is typically
        overridden by a derived class to perform this function.
        """
        _logger.debug("encode")
        # by default do nothing, the arguments have already been supplied

    def decode(self):
        """
        This method is called to transform the result or error returned by
        the other controller into something suitable to return.  It is typically
        overridden by a derived class to perform this function.
        """
        _logger.debug("decode")
        # refer to the chained iocb
        iocb = self.ioChain
        # if this has completed successfully, pass it up
        if self.io_state == COMPLETED:
            _logger.debug("    - completed: %r", self.io_response)
            # change the state and transform the content
            iocb.io_state = COMPLETED
            iocb.io_response = self.io_response
        # if this aborted, pass that up too
        elif self.io_state == ABORTED:
            _logger.debug("    - aborted: %r", self.io_error)
            # change the state
            iocb.io_state = ABORTED
            iocb.io_error = self.io_error
        else:
            raise RuntimeError("invalid state: %d" % (self.io_state,))
