
import asyncio
import logging
from ..comm import IOQController, IOCB
from ..apdu import UnconfirmedRequestPDU, SimpleAckPDU, ComplexAckPDU, ErrorPDU, RejectPDU, AbortPDU
from ..apdu.util import get_apdu_value
from .app import Application

_logger = logging.getLogger(__name__)
__all__ = ['ApplicationIOController']


class ApplicationIOController(IOQController, Application):
    """
    Application IO Controller.
    This IO Controller has queues IO requests so that there is only one request running
    for every unique destination address.
    """
    def __init__(self, *args, **kwargs):
        IOQController.__init__(self)
        Application.__init__(self, *args, **kwargs)
        # We have to keep track of all the active IOCBs so that
        # confirmations can be assigned to the requesting iocb
        self.active_iocbs = {}

    def _process_io(self, iocb: IOCB):
        self.active_io(iocb)
        self.request(iocb.request)

    def active_io(self, iocb: IOCB):
        self.active_iocbs[iocb.request.pduDestination] = iocb
        IOQController.active_io(self, iocb)

    def complete_io(self, iocb: IOCB, msg):
        self.active_iocbs.pop(iocb.request.pduDestination)
        IOQController.complete_io(self, iocb, msg)

    def abort_io(self, iocb: IOCB, err):
        self.active_iocbs.pop(iocb.request.pduDestination)
        IOQController.abort_io(self, iocb, err)

    def _app_complete(self, address, apdu):
        # look up the queue
        iocb = self.active_iocbs.get(address)
        # make sure it has an active iocb
        if not iocb:
            _logger.error('no active request for %r %r', address, self.active_iocbs)
            return
        # this request is complete
        if isinstance(apdu, (None.__class__, SimpleAckPDU, ComplexAckPDU)):
            self.complete_io(iocb, apdu)
        elif isinstance(apdu, (ErrorPDU, RejectPDU, AbortPDU)):
            self.abort_io(iocb, apdu)
        else:
            raise RuntimeError('unrecognized APDU type')

    def request(self, apdu):
        # send it downstream
        super(ApplicationIOController, self).request(apdu)
        # if this was an unconfirmed request, it's complete, no message
        if isinstance(apdu, UnconfirmedRequestPDU):
            self._app_complete(apdu.pduDestination, None)

    def confirmation(self, apdu):
        # this is an ack, error, reject or abort
        self._app_complete(apdu.pduSource, apdu)

    async def execute_request(self, request, throw_on_error=False):
        """
        Execute the given request and return the result when finished.
        :param request: APDU request instance
        :param throw_on_error: Abort on the first error and throw
        :return: result value (None if unconfirmed request)
        """
        iocb = IOCB(request)
        self.request_io(iocb)
        await iocb.wait()
        return get_apdu_value(iocb.io_response)

    async def execute_requests(self, requests, throw_on_error=False):
        iocbs = [IOCB(request) for request in requests]
        for iocb in iocbs:
            self.request_io(iocb)
        results = []
        for iocb in iocbs:
            await iocb.wait()
            results.append(get_apdu_value(iocb.io_response))
        return results
