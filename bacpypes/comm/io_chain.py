import logging

from ..debugging import DebugContents
from .iocb import IOCB
from .iocb_states import *

_logger = logging.getLogger(__name__)
__all__ = ['IOChain']


class IOChain(IOCB, DebugContents):
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
        chain.ioController = self
        # consider the parent active
        chain.ioState = ACTIVE
        try:
            _logger.debug("    - encoding")
            # let the derived class set the args and kwargs
            self.encode()
            _logger.debug("    - encode complete")
        except Exception as e:
            # extract the error and abort the request
            _logger.exception("    - encoding exception: %r", e)
            chain.abort(e)

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
        except Exception as e:
            # extract the error and abort
            _logger.exception("    - decoding exception: %r", e)
            iocb.ioState = ABORTED
            iocb.ioError = e
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
        """Hook to transform the request, called when this IOCB is chained."""
        _logger.debug("encode")
        # by default do nothing, the arguments have already been supplied

    def decode(self):
        """Hook to transform the response, called when this IOCB is completed."""
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
