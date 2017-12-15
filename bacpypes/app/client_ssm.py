
import logging
from ..apdu import AbortPDU, AbortReason, ComplexAckPDU, ConfirmedRequestPDU, ErrorPDU, RejectPDU, SegmentAckPDU, SimpleAckPDU
from .ssm import SSM
from .ssm_states import *

_logger = logging.getLogger(__name__)
__all__ = ['ClientSSM']


class ClientSSM(SSM):
    """
    ClientSSM - Client Segmentation State Machine
    """

    def __init__(self, sap, remoteDevice):
        SSM.__init__(self, sap, remoteDevice)
        # initialize the retry count
        self.retryCount = 0

    def set_state(self, new_state, timer=0):
        """This function is called when the client wants to change state."""
        # do the regular state change
        SSM.set_state(self, new_state, timer)
        # when completed or aborted, remove tracking
        if (new_state == COMPLETED) or (new_state == ABORTED):
            self.ssmSAP.clientTransactions.remove(self)
            self.ssmSAP.deviceInfoCache.release_device_info(self.remoteDevice)

    def request(self, apdu):
        """
        This function is called by client transaction functions when it wants to send a message to the device.
        """
        # make sure it has a good source and destination
        apdu.pduSource = None
        apdu.pduDestination = self.remoteDevice.address
        # send it via the device
        self.ssmSAP.request(apdu)

    def indication(self, apdu):
        """
        This function is called after the device has bound a new transaction
        and wants to start the process rolling.
        """
        # make sure we're getting confirmed requests
        if apdu.apduType != ConfirmedRequestPDU.pduType:
            raise RuntimeError('invalid APDU (1)')
        # save the request and set the segmentation context
        self.set_segmentation_context(apdu)
        # the segment size is the minimum of the maximum size I can transmit,
        # the maximum conveyable by the internetwork to the remote device, and
        # the maximum APDU size accepted by the remote device.
        self.segmentSize = min(
            self.ssmSAP.maxApduLengthAccepted,
            self.remoteDevice.maxNpduLength,
            self.remoteDevice.maxApduLengthAccepted
        )
        # the maximum number of segments acceptable in the reply
        if apdu.apduMaxSegs is not None:
            # this request overrides the default
            self.maxSegmentsAccepted = apdu.apduMaxSegs
        # save the invoke ID
        self.invokeID = apdu.apduInvokeID
        # compute the segment count ### minus the header?
        if not apdu.pduData:
            # always at least one segment
            self.segmentCount = 1
        else:
            # split into chunks, maybe need one more
            self.segmentCount, more = divmod(len(apdu.pduData), self.segmentSize)
            if more:
                self.segmentCount += 1
        # make sure we support segmented transmit if we need to
        if self.segmentCount > 1:
            if self.ssmSAP.segmentationSupported not in ('segmentedTransmit', 'segmentedBoth'):
                # local device can't send segmented requests
                abort = self.abort(AbortReason.segmentationNotSupported)
                self.response(abort)
                return
            if self.remoteDevice.segmentationSupported not in ('segmentedReceive', 'segmentedBoth'):
                # remote device can't receive segmented requests
                abort = self.abort(AbortReason.segmentationNotSupported)
                self.response(abort)
                return

        # ToDo: check for APDUTooLong?

        # send out the first segment (or the whole thing)
        if self.segmentCount == 1:
            # SendConfirmedUnsegmented
            self.sentAllSegments = True
            self.retryCount = 0
            self.set_state(AWAIT_CONFIRMATION, self.ssmSAP.retryTimeout)
        else:
            # SendConfirmedSegmented
            self.sentAllSegments = False
            self.retryCount = 0
            self.segmentRetryCount = 0
            self.initialSequenceNumber = 0
            self.proposedWindowSize = self.ssmSAP.maxSegmentsAccepted
            self.actualWindowSize = 1
            self.set_state(SEGMENTED_REQUEST, self.ssmSAP.segmentTimeout)

        # deliver to the device
        self.request(self.get_segment(0))

    def response(self, apdu):
        """
        This function is called by client transaction functions when they want to send a message to the application.
        """
        # make sure it has a good source and destination
        apdu.pduSource = self.remoteDevice.address
        apdu.pduDestination = None
        # send it to the application
        self.ssmSAP.sap_response(apdu)

    def confirmation(self, apdu):
        """
        This function is called by the device for all upstream messages related to the transaction.
        """
        if self.state == SEGMENTED_REQUEST:
            self.segmented_request(apdu)
        elif self.state == AWAIT_CONFIRMATION:
            self.await_confirmation(apdu)
        elif self.state == SEGMENTED_CONFIRMATION:
            self.segmented_confirmation(apdu)
        else:
            raise RuntimeError('invalid state')

    def handle_timeout(self):
        """This function is called when something has taken too long."""
        if self.state == SEGMENTED_REQUEST:
            self.segmented_request_timeout()
        elif self.state == AWAIT_CONFIRMATION:
            self.await_confirmation_timeout()
        elif self.state == SEGMENTED_CONFIRMATION:
            self.segmented_confirmation_timeout()
        elif self.state == COMPLETED:
            pass
        elif self.state == ABORTED:
            pass
        else:
            e = RuntimeError('invalid state')
            _logger.exception(f'exception: {e!r}')
            raise e

    def abort(self, reason):
        """This function is called when the transaction should be aborted."""
        # change the state to aborted
        self.set_state(ABORTED)
        # build an abort PDU to return
        abort_pdu = AbortPDU(False, self.invokeID, reason)
        return abort_pdu

    def segmented_request(self, apdu):
        """
        This function is called when the client is sending a segmented request and receives an apdu.
        """
        # client is ready for the next segment
        if apdu.apduType == SegmentAckPDU.pduType:
            # duplicate ack received?
            if not self.in_window(apdu.apduSeq, self.initialSequenceNumber):
                # not in window
                self.restart_timer(self.ssmSAP.segmentTimeout)
            # final ack received?
            elif self.sentAllSegments:
                # all done sending request
                self.set_state(AWAIT_CONFIRMATION, self.ssmSAP.retryTimeout)
            else:
                # more segments to send
                self.initialSequenceNumber = (apdu.apduSeq + 1) % 256
                self.actualWindowSize = apdu.apduWin
                self.segmentRetryCount = 0
                self.FillWindow(self.initialSequenceNumber)
                self.restart_timer(self.ssmSAP.segmentTimeout)

        # simple ack
        elif apdu.apduType == SimpleAckPDU.pduType:
            if not self.sentAllSegments:
                abort = self.abort(AbortReason.invalidApduInThisState)
                self.request(abort)  # send it to the device
                self.response(abort)  # send it to the application
            else:
                self.set_state(COMPLETED)
                self.response(apdu)

        elif apdu.apduType == ComplexAckPDU.pduType:
            if not self.sentAllSegments:
                abort = self.abort(AbortReason.invalidApduInThisState)
                self.request(abort)  # send it to the device
                self.response(abort)  # send it to the application

            elif not apdu.apduSeg:
                self.set_state(COMPLETED)
                self.response(apdu)
            else:
                # set the segmented response context
                self.set_segmentation_context(apdu)
                self.actualWindowSize = min(apdu.apduWin, self.ssmSAP.maxSegmentsAccepted)
                self.lastSequenceNumber = 0
                self.initialSequenceNumber = 0
                self.set_state(SEGMENTED_CONFIRMATION, self.ssmSAP.segmentTimeout)

        # some kind of problem
        elif (apdu.apduType == ErrorPDU.pduType) or (apdu.apduType == RejectPDU.pduType) or (
                apdu.apduType == AbortPDU.pduType):
            # error/reject/abort
            self.set_state(COMPLETED)
            self.response = apdu
            self.response(apdu)
        else:
            raise RuntimeError('invalid APDU (2)')

    def segmented_request_timeout(self):
        # try again
        if self.segmentRetryCount < self.ssmSAP.retryCount:
            # retry segmented request
            self.segmentRetryCount += 1
            self.start_timer(self.ssmSAP.segmentTimeout)
            self.FillWindow(self.initialSequenceNumber)
        else:
            # abort, no response from the device
            abort = self.abort(AbortReason.noResponse)
            self.response(abort)

    def await_confirmation(self, apdu):
        if apdu.apduType == AbortPDU.pduType:
            # server aborted
            self.set_state(ABORTED)
            self.response(apdu)

        elif (apdu.apduType == SimpleAckPDU.pduType) or (apdu.apduType == ErrorPDU.pduType) or (
                apdu.apduType == RejectPDU.pduType):
            # simple ack, error, or reject
            self.set_state(COMPLETED)
            self.response(apdu)

        elif apdu.apduType == ComplexAckPDU.pduType:
            # complex ack
            # if the response is not segmented, we're done
            if not apdu.apduSeg:
                # unsegmented
                self.set_state(COMPLETED)
                self.response(apdu)
            elif self.ssmSAP.segmentationSupported not in ('segmentedReceive', 'segmentedBoth'):
                # local device can't receive segmented messages
                abort = self.abort(AbortReason.segmentationNotSupported)
                self.response(abort)
            elif apdu.apduSeq == 0:
                # segmented response
                # set the segmented response context
                self.set_segmentation_context(apdu)
                self.actualWindowSize = min(apdu.apduWin, self.ssmSAP.maxSegmentsAccepted)
                self.lastSequenceNumber = 0
                self.initialSequenceNumber = 0
                self.set_state(SEGMENTED_CONFIRMATION, self.ssmSAP.segmentTimeout)
                # send back a segment ack
                segack = SegmentAckPDU(0, 0, self.invokeID, self.initialSequenceNumber, self.actualWindowSize)
                self.request(segack)
            else:
                # invalid APDU in this state
                abort = self.abort(AbortReason.invalidApduInThisState)
                # send it to the device
                self.request(abort)
                # send it to the application
                self.response(abort)

        elif apdu.apduType == SegmentAckPDU.pduType:
            # segment ack(!?)
            self.restart_timer(self.ssmSAP.segmentTimeout)
        else:
            raise RuntimeError('invalid APDU (3)')

    def await_confirmation_timeout(self):
        self.retryCount += 1
        if self.retryCount < self.ssmSAP.retryCount:
            # no response, try again
            # save the retry count, indication acts like the request is coming
            # from the application so the retryCount gets re-initialized.
            save_count = self.retryCount
            self.indication(self.segmentAPDU)
            self.retryCount = save_count
        else:
            # retry count exceeded
            abort = self.abort(AbortReason.noResponse)
            self.response(abort)

    def segmented_confirmation(self, apdu):
        # the only messages we should be getting are complex acks
        if (apdu.apduType != ComplexAckPDU.pduType):
            # complex ack required
            abort = self.abort(AbortReason.invalidApduInThisState)
            # send it to the device
            self.request(abort)
            # send it to the application
            self.response(abort)
            return

        # it must be segmented
        if not apdu.apduSeg:
            abort = self.abort(AbortReason.invalidApduInThisState)
            self.request(abort)
            self.response(abort)
            return

        # proper segment number
        if apdu.apduSeq != (self.lastSequenceNumber + 1) % 256:
            # segment received out of order
            self.restart_timer(self.ssmSAP.segmentTimeout)
            segack = SegmentAckPDU(1, 0, self.invokeID, self.lastSequenceNumber, self.actualWindowSize)
            self.request(segack)
            return
        # add the data
        self.append_segment(apdu)
        # update the sequence number
        self.lastSequenceNumber = (self.lastSequenceNumber + 1) % 256
        # last segment received
        if not apdu.apduMor:
            # no more follows
            # send a final ack
            segack = SegmentAckPDU(0, 0, self.invokeID, self.lastSequenceNumber, self.actualWindowSize)
            self.request(segack)
            self.set_state(COMPLETED)
            self.response(self.segmentAPDU)

        elif apdu.apduSeq == ((self.initialSequenceNumber + self.actualWindowSize) % 256):
            # last segment in the group
            self.initialSequenceNumber = self.lastSequenceNumber
            self.restart_timer(self.ssmSAP.segmentTimeout)
            segack = SegmentAckPDU(0, 0, self.invokeID, self.lastSequenceNumber, self.actualWindowSize)
            self.request(segack)

        else:
            # wait for more segments
            self.restart_timer(self.ssmSAP.segmentTimeout)

    def segmented_confirmation_timeout(self):
        abort = self.abort(AbortReason.noResponse)
        self.response(abort)
