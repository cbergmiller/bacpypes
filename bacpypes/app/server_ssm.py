import logging
from ..apdu import AbortPDU, AbortReason, ComplexAckPDU, ConfirmedRequestPDU, ErrorPDU, RejectPDU, SegmentAckPDU, \
    SimpleAckPDU, decode_max_segments_accepted, decode_max_apdu_length_accepted
from .ssm import SSM
from .ssm_states import *

_logger = logging.getLogger(__name__)
__all__ = ['ServerSSM']


class ServerSSM(SSM):

    def __init__(self, sap, pdu_address):
        _logger.debug("__init__ %s %r", sap, pdu_address)
        SSM.__init__(self, sap, pdu_address)

        # acquire the device info
        if self.device_info:
            _logger.debug("    - acquire device information")
            self.ssmSAP.deviceInfoCache.acquire(self.device_info)

    def set_state(self, newState, timer=0):
        """This function is called when the client wants to change state."""
        _logger.debug("set_state %r (%s) timer=%r", newState, SSM.transactionLabels[newState], timer)

        # do the regular state change
        SSM.set_state(self, newState, timer)

        # when completed or aborted, remove tracking
        if (newState == COMPLETED) or (newState == ABORTED):
            _logger.debug("    - remove from active transactions")
            self.ssmSAP.serverTransactions.remove(self)

            # release the device info
            if self.device_info:
                _logger.debug("    - release device information")
                self.ssmSAP.deviceInfoCache.release(self.device_info)

    def request(self, apdu):
        """This function is called by transaction functions to send
        to the application."""
        _logger.debug("request %r", apdu)

        # make sure it has a good source and destination
        apdu.pduSource = self.pdu_address
        apdu.pduDestination = None

        # send it via the device
        self.ssmSAP.sap_request(apdu)

    def indication(self, apdu):
        """This function is called for each downstream packet related to
        the transaction."""
        _logger.debug("indication %r", apdu)

        if self.state == IDLE:
            self.idle(apdu)
        elif self.state == SEGMENTED_REQUEST:
            self.segmented_request(apdu)
        elif self.state == AWAIT_RESPONSE:
            self.await_response(apdu)
        elif self.state == SEGMENTED_RESPONSE:
            self.segmented_response(apdu)
        else:
            _logger.debug("    - invalid state")

    def response(self, apdu):
        """This function is called by transaction functions when they want
        to send a message to the device."""
        _logger.debug("response %r", apdu)

        # make sure it has a good source and destination
        apdu.pduSource = None
        apdu.pduDestination = self.pdu_address

        # send it via the device
        self.ssmSAP.request(apdu)

    def confirmation(self, apdu):
        """This function is called when the application has provided a response
        and needs it to be sent to the client."""
        _logger.debug("confirmation %r", apdu)

        # check to see we are in the correct state
        if self.state != AWAIT_RESPONSE:
            _logger.debug("    - warning: not expecting a response")

        # abort response
        if (apdu.apduType == AbortPDU.pduType):
            _logger.debug("    - abort")

            self.set_state(ABORTED)

            # send the response to the device
            self.response(apdu)
            return

        # simple response
        if (apdu.apduType == SimpleAckPDU.pduType) or (apdu.apduType == ErrorPDU.pduType) or (apdu.apduType == RejectPDU.pduType):
            _logger.debug("    - simple ack, error, or reject")

            # transaction completed
            self.set_state(COMPLETED)

            # send the response to the device
            self.response(apdu)
            return

        # complex ack
        if (apdu.apduType == ComplexAckPDU.pduType):
            _logger.debug("    - complex ack")

            # save the response and set the segmentation context
            self.set_segmentation_context(apdu)

            # the segment size is the minimum of the size of the largest packet
            # that can be delivered to the client and the largest it can accept
            if (not self.device_info) or (self.device_info.maxNpduLength is None):
                self.segmentSize = self.maxApduLengthAccepted
            else:
                self.segmentSize = min(self.device_info.maxNpduLength, self.maxApduLengthAccepted)
            _logger.debug("    - segment size: %r", self.segmentSize)

            # compute the segment count
            if not apdu.pduData:
                # always at least one segment
                self.segmentCount = 1
            else:
                # split into chunks, maybe need one more
                self.segmentCount, more = divmod(len(apdu.pduData), self.segmentSize)
                if more:
                    self.segmentCount += 1
            _logger.debug("    - segment count: %r", self.segmentCount)

            # make sure we support segmented transmit if we need to
            if self.segmentCount > 1:
                _logger.debug("    - segmentation required, %d segments", self.segmentCount)

                # make sure we support segmented transmit
                if self.segmentationSupported not in ('segmentedTransmit', 'segmentedBoth'):
                    _logger.debug("    - server can't send segmented responses")
                    abort = self.abort(AbortReason.segmentationNotSupported)
                    self.response(abort)
                    return

                # make sure client supports segmented receive
                if self.device_info.segmentationSupported not in ('segmentedReceive', 'segmentedBoth'):
                    _logger.debug("    - client can't receive segmented responses")
                    abort = self.abort(AbortReason.segmentationNotSupported)
                    self.response(abort)
                    return

                # make sure we dont exceed the number of segments in our response
                # that the device said it was willing to accept in the request
                if self.segmentCount > self.maxSegmentsAccepted:
                    _logger.debug("    - client can't receive enough segments")
                    abort = self.abort(AbortReason.apduTooLong)
                    self.response(abort)
                    return

            # initialize the state
            self.segmentRetryCount = 0
            self.initialSequenceNumber = 0
            self.actualWindowSize = None

            # send out the first segment (or the whole thing)
            if self.segmentCount == 1:
                self.response(apdu)
                self.set_state(COMPLETED)
            else:
                self.response(self.get_segment(0))
                self.set_state(SEGMENTED_RESPONSE, self.segmentTimeout)

        else:
            raise RuntimeError("invalid APDU (4)")

    def process_task(self):
        """This function is called when the client has failed to send all of the
        segments of a segmented request, the application has taken too long to
        complete the request, or the client failed to ack the segments of a
        segmented response."""
        _logger.debug("process_task")

        if self.state == SEGMENTED_REQUEST:
            self.segmented_request_timeout()
        elif self.state == AWAIT_RESPONSE:
            self.await_response_timeout()
        elif self.state == SEGMENTED_RESPONSE:
            self.segmented_response_timeout()
        elif self.state == COMPLETED:
            pass
        elif self.state == ABORTED:
            pass
        else:
            _logger.debug("invalid state")
            raise RuntimeError("invalid state")

    def abort(self, reason):
        """This function is called when the application would like to abort the
        transaction.  There is no notification back to the application."""
        _logger.debug("abort %r", reason)

        # change the state to aborted
        self.set_state(ABORTED)

        # return an abort APDU
        return AbortPDU(True, self.invokeID, reason)

    def idle(self, apdu):
        _logger.debug("idle %r", apdu)

        # make sure we're getting confirmed requests
        if not isinstance(apdu, ConfirmedRequestPDU):
            raise RuntimeError("invalid APDU (5)")

        # save the invoke ID
        self.invokeID = apdu.apduInvokeID
        _logger.debug("    - invoke ID: %r", self.invokeID)

        if apdu.apduSA:
            if not self.device_info:
                _logger.debug("    - no client device info")

            elif self.device_info.segmentationSupported == 'noSegmentation':
                _logger.debug("    - client actually supports segmented receive")
                self.device_info.segmentationSupported = 'segmentedReceive'

                _logger.debug("    - tell the cache the info has been updated")
                self.ssmSAP.deviceInfoCache.update_device_info(self.device_info)

            elif self.device_info.segmentationSupported == 'segmentedTransmit':
                _logger.debug("    - client actually supports both segmented transmit and receive")
                self.device_info.segmentationSupported = 'segmentedBoth'

                _logger.debug("    - tell the cache the info has been updated")
                self.ssmSAP.deviceInfoCache.update_device_info(self.device_info)

            elif self.device_info.segmentationSupported == 'segmentedReceive':
                pass

            elif self.device_info.segmentationSupported == 'segmentedBoth':
                pass

            else:
                raise RuntimeError("invalid segmentation supported in device info")

        # decode the maximum that the client can receive in one APDU, and if
        # there is a value in the device information then use that one because
        # it came from reading device object property value or from an I-Am
        # message that was received
        self.maxApduLengthAccepted = decode_max_apdu_length_accepted(apdu.apduMaxResp)
        if self.device_info and self.device_info.maxApduLengthAccepted is not None:
            if self.device_info.maxApduLengthAccepted < self.maxApduLengthAccepted:
                _logger.debug("    - apduMaxResp encoding error")
            else:
                self.maxApduLengthAccepted = self.device_info.maxApduLengthAccepted
        _logger.debug("    - maxApduLengthAccepted: %r", self.maxApduLengthAccepted)

        # save the number of segments the client is willing to accept in the ack,
        # if this is None then the value is unknown or more than 64
        self.maxSegmentsAccepted = decode_max_segments_accepted(apdu.apduMaxSegs)

        # unsegmented request
        if not apdu.apduSeg:
            self.set_state(AWAIT_RESPONSE, self.ssmSAP.applicationTimeout)
            self.request(apdu)
            return

        # make sure we support segmented requests
        if self.segmentationSupported not in ('segmentedReceive', 'segmentedBoth'):
            abort = self.abort(AbortReason.segmentationNotSupported)
            self.response(abort)
            return

        # save the request and set the segmentation context
        self.set_segmentation_context(apdu)

        # the window size is the minimum of what I would propose and what the
        # device has proposed
        self.actualWindowSize = min(apdu.apduWin, self.proposedWindowSize)
        _logger.debug("    - actualWindowSize? min(%r, %r) -> %r", apdu.apduWin, self.proposedWindowSize, self.actualWindowSize)

        # initialize the state
        self.lastSequenceNumber = 0
        self.initialSequenceNumber = 0
        self.set_state(SEGMENTED_REQUEST, self.segmentTimeout)

        # send back a segment ack
        segack = SegmentAckPDU(0, 1, self.invokeID, self.initialSequenceNumber, self.actualWindowSize)
        _logger.debug("    - segAck: %r", segack)

        self.response(segack)

    def segmented_request(self, apdu):
        _logger.debug("segmented_request %r", apdu)

        # some kind of problem
        if (apdu.apduType == AbortPDU.pduType):
            self.set_state(COMPLETED)
            self.response(apdu)
            return

        # the only messages we should be getting are confirmed requests
        elif (apdu.apduType != ConfirmedRequestPDU.pduType):
            abort = self.abort(AbortReason.invalidApduInThisState)
            self.request(abort) # send it to the device
            self.response(abort) # send it to the application
            return

        # it must be segmented
        elif not apdu.apduSeg:
            abort = self.abort(AbortReason.invalidApduInThisState)
            self.request(abort) # send it to the application
            self.response(abort) # send it to the device
            return

        # proper segment number
        if apdu.apduSeq != (self.lastSequenceNumber + 1) % 256:
            _logger.debug("    - segment %d received out of order, should be %d", apdu.apduSeq, (self.lastSequenceNumber + 1) % 256)

            # segment received out of order
            self.restart_timer(self.segmentTimeout)

            # send back a segment ack
            segack = SegmentAckPDU(1, 1, self.invokeID, self.initialSequenceNumber, self.actualWindowSize)

            self.response(segack)
            return

        # add the data
        self.append_segment(apdu)

        # update the sequence number
        self.lastSequenceNumber = (self.lastSequenceNumber + 1) % 256

        # last segment?
        if not apdu.apduMor:
            _logger.debug("    - no more follows")

            # send back a final segment ack
            segack = SegmentAckPDU(0, 1, self.invokeID, self.lastSequenceNumber, self.actualWindowSize)
            self.response(segack)

            # forward the whole thing to the application
            self.set_state(AWAIT_RESPONSE, self.ssmSAP.applicationTimeout)
            self.request(self.segmentAPDU)

        elif apdu.apduSeq == ((self.initialSequenceNumber + self.actualWindowSize) % 256):
                _logger.debug("    - last segment in the group")

                self.initialSequenceNumber = self.lastSequenceNumber
                self.restart_timer(self.segmentTimeout)

                # send back a segment ack
                segack = SegmentAckPDU(0, 1, self.invokeID, self.initialSequenceNumber, self.actualWindowSize)
                self.response(segack)

        else:
            # wait for more segments
            _logger.debug("    - wait for more segments")

            self.restart_timer(self.segmentTimeout)

    def segmented_request_timeout(self):
        _logger.debug("segmented_request_timeout")

        # give up
        self.set_state(ABORTED)

    def await_response(self, apdu):
        _logger.debug("await_response %r", apdu)

        if isinstance(apdu, ConfirmedRequestPDU):
            _logger.debug("    - client is trying this request again")

        elif isinstance(apdu, AbortPDU):
            _logger.debug("    - client aborting this request")

            # forward abort to the application
            self.set_state(ABORTED)
            self.request(apdu)

        else:
            raise RuntimeError("invalid APDU (6)")

    def await_response_timeout(self):
        """This function is called when the application has taken too long
        to respond to a clients request.  The client has probably long since
        given up."""
        _logger.debug("await_response_timeout")

        abort = self.abort(AbortReason.serverTimeout)
        self.request(abort)

    def segmented_response(self, apdu):
        _logger.debug("segmented_response %r", apdu)

        # client is ready for the next segment
        if (apdu.apduType == SegmentAckPDU.pduType):
            _logger.debug("    - segment ack")

            # actual window size is provided by client
            self.actualWindowSize = apdu.apduWin

            # duplicate ack received?
            if not self.in_window(apdu.apduSeq, self.initialSequenceNumber):
                _logger.debug("    - not in window")
                self.restart_timer(self.segmentTimeout)

            # final ack received?
            elif self.sentAllSegments:
                _logger.debug("    - all done sending response")
                self.set_state(COMPLETED)

            else:
                _logger.debug("    - more segments to send")

                self.initialSequenceNumber = (apdu.apduSeq + 1) % 256
                self.actualWindowSize = apdu.apduWin
                self.segmentRetryCount = 0
                self.fill_window(self.initialSequenceNumber)
                self.restart_timer(self.segmentTimeout)

        # some kind of problem
        elif (apdu.apduType == AbortPDU.pduType):
            self.set_state(COMPLETED)
            self.response(apdu)

        else:
            raise RuntimeError("invalid APDU (7)")

    def segmented_response_timeout(self):
        _logger.debug("segmented_response_timeout")

        # try again
        if self.segmentRetryCount < self.numberOfApduRetries:
            self.segmentRetryCount += 1
            self.start_timer(self.segmentTimeout)
            self.fill_window(self.initialSequenceNumber)
        else:
            # give up
            self.set_state(ABORTED)