
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

    def __init__(self, sap, pdu_address):
        SSM.__init__(self, sap, pdu_address)
        # initialize the retry count
        self.retryCount = 0
        # acquire the device info
        if self.device_info:
            self.ssmSAP.deviceInfoCache.acquire(self.device_info)

    def set_state(self, new_state, timer=0):
        """This function is called when the client wants to change state."""
        # do the regular state change
        SSM.set_state(self, new_state, timer)
        # when completed or aborted, remove tracking
        if (new_state == COMPLETED) or (new_state == ABORTED):
            self.ssmSAP.clientTransactions.remove(self)
            # release the device info
            if self.device_info:
                self.ssmSAP.deviceInfoCache.release(self.device_info)

    def request(self, apdu):
        """
        This function is called by client transaction functions when it wants to send a message to the device.
        """
        # make sure it has a good source and destination
        apdu.pduSource = None
        apdu.pduDestination = self.pdu_address
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
        # if the max apdu length of the server isn't known, assume that it
        # is the same size as our own and will be the segment size
        if (not self.device_info) or (self.device_info.maxApduLengthAccepted is None):
            self.segmentSize = self.maxApduLengthAccepted
        # if the max npdu length of the server isn't known, assume that it
        # is the same as the max apdu length accepted
        elif self.device_info.maxNpduLength is None:
            self.segmentSize = self.device_info.maxApduLengthAccepted
        # the segment size is the minimum of the size of the largest packet
        # that can be delivered to the server and the largest it can accept
        else:
            self.segmentSize = min(self.device_info.maxNpduLength, self.device_info.maxApduLengthAccepted)
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
            if self.segmentationSupported not in ('segmentedTransmit', 'segmentedBoth'):
                # local device can't send segmented requests
                abort = self.abort(AbortReason.segmentationNotSupported)
                self.response(abort)
                return
            if not self.device_info:
                _logger.debug("    - no server info for segmentation support")
            elif self.device_info.segmentationSupported not in ('segmentedReceive', 'segmentedBoth'):
                abort = self.abort(AbortReason.segmentationNotSupported)
                self.response(abort)
                return

            # make sure we dont exceed the number of segments in our request
            # that the server said it was willing to accept
            if not self.device_info:
                _logger.debug("    - no server info for maximum number of segments")
            elif not self.device_info.maxSegmentsAccepted:
                _logger.debug("    - server doesn't say maximum number of segments")
            elif self.segmentCount > self.device_info.maxSegmentsAccepted:
                _logger.debug("    - server can't receive enough segments")
                abort = self.abort(AbortReason.apduTooLong)
                self.response(abort)
                return

        # send out the first segment (or the whole thing)
        if self.segmentCount == 1:
            # unsegmented
            self.sentAllSegments = True
            self.retryCount = 0
            self.set_state(AWAIT_CONFIRMATION, self.apduTimeout)
        else:
            # segmented
            self.sentAllSegments = False
            self.retryCount = 0
            self.segmentRetryCount = 0
            self.initialSequenceNumber = 0
            self.actualWindowSize = None    # segment ack will set value
            self.set_state(SEGMENTED_REQUEST, self.segmentTimeout)


        # deliver to the device
        self.request(self.get_segment(0))

    def response(self, apdu):
        """
        This function is called by client transaction functions when they want to send a message to the application.
        """
        # make sure it has a good source and destination
        apdu.pduSource = self.pdu_address
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
            _logger.exception('exception: %r', e)
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
        # server is ready for the next segment
        if apdu.apduType == SegmentAckPDU.pduType:
            # actual window size is provided by server
            self.actualWindowSize = apdu.apduWin
            # duplicate ack received?
            if not self.in_window(apdu.apduSeq, self.initialSequenceNumber):
                # not in window
                self.restart_timer(self.segmentTimeout)
            # final ack received?
            elif self.sentAllSegments:
                # all done sending request
                self.set_state(AWAIT_CONFIRMATION, self.apduTimeout)
            else:
                # more segments to send
                self.initialSequenceNumber = (apdu.apduSeq + 1) % 256

                self.segmentRetryCount = 0
                self.fill_window(self.initialSequenceNumber)
                self.restart_timer(self.segmentTimeout)

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
                # ack is not segmented
                self.set_state(COMPLETED)
                self.response(apdu)
            else:
                # set the segmented response context
                self.set_segmentation_context(apdu)
                # minimum of what the server is proposing and this client proposes
                self.actualWindowSize = min(apdu.apduWin, self.proposedWindowSize)
                self.lastSequenceNumber = 0
                self.initialSequenceNumber = 0
                self.set_state(SEGMENTED_CONFIRMATION, self.segmentTimeout)

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
        if self.segmentRetryCount < self.numberOfApduRetries:
            # retry segmented request
            self.segmentRetryCount += 1
            self.start_timer(self.segmentTimeout)
            self.fill_window(self.initialSequenceNumber)
        else:
            # abort, no response from the device
            abort = self.abort(AbortReason.noResponse)
            self.response(abort)

    def await_confirmation(self, apdu):
        _logger.debug("await_confirmation %r", apdu)

        if (apdu.apduType == AbortPDU.pduType):
            _logger.debug("    - server aborted")

            self.set_state(ABORTED)
            self.response(apdu)

        elif (apdu.apduType == SimpleAckPDU.pduType) or (apdu.apduType == ErrorPDU.pduType) or (
                apdu.apduType == RejectPDU.pduType):
            _logger.debug("    - simple ack, error, or reject")

            self.set_state(COMPLETED)
            self.response(apdu)

        elif (apdu.apduType == ComplexAckPDU.pduType):
            _logger.debug("    - complex ack")

            # if the response is not segmented, we're done
            if not apdu.apduSeg:
                _logger.debug("    - unsegmented")

                self.set_state(COMPLETED)
                self.response(apdu)

            elif self.segmentationSupported not in ('segmentedReceive', 'segmentedBoth'):
                _logger.debug("    - local device can't receive segmented messages")
                abort = self.abort(AbortReason.segmentationNotSupported)
                self.response(abort)

            elif apdu.apduSeq == 0:
                _logger.debug("    - segmented response")

                # set the segmented response context
                self.set_segmentation_context(apdu)

                self.actualWindowSize = apdu.apduWin
                self.lastSequenceNumber = 0
                self.initialSequenceNumber = 0
                self.set_state(SEGMENTED_CONFIRMATION, self.segmentTimeout)

                # send back a segment ack
                segack = SegmentAckPDU(0, 0, self.invokeID, self.initialSequenceNumber, self.actualWindowSize)
                self.request(segack)

            else:
                _logger.debug("    - invalid APDU in this state")

                abort = self.abort(AbortReason.invalidApduInThisState)
                self.request(abort)  # send it to the device
                self.response(abort)  # send it to the application

        elif (apdu.apduType == SegmentAckPDU.pduType):
            _logger.debug("    - segment ack(!?)")

            self.restart_timer(self.segmentTimeout)

        else:
            raise RuntimeError("invalid APDU (3)")

    def await_confirmation_timeout(self):
        _logger.debug("await_confirmation_timeout")

        if self.retryCount < self.numberOfApduRetries:
            _logger.debug("    - no response, try again (%d < %d)", self.retryCount,
                self.numberOfApduRetries)
            self.retryCount += 1

            # save the retry count, indication acts like the request is coming
            # from the application so the retryCount gets re-initialized.
            saveCount = self.retryCount
            self.indication(self.segmentAPDU)
            self.retryCount = saveCount
        else:
            _logger.debug("    - retry count exceeded")
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
            self.restart_timer(self.segmentTimeout)
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
            self.restart_timer(self.segmentTimeout)
            segack = SegmentAckPDU(0, 0, self.invokeID, self.lastSequenceNumber, self.actualWindowSize)
            self.request(segack)

        else:
            # wait for more segments
            self.restart_timer(self.segmentTimeout)

    def segmented_confirmation_timeout(self):
        abort = self.abort(AbortReason.noResponse)
        self.response(abort)
