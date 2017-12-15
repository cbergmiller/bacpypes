import logging
from ..apdu import AbortPDU, AbortReason, ComplexAckPDU, ConfirmedRequestPDU, ErrorPDU, RejectPDU, SegmentAckPDU, \
    SimpleAckPDU
from .ssm import SSM
from .ssm_states import *

_logger = logging.getLogger(__name__)
__all__ = ['ServerSSM']


class ServerSSM(SSM):
    """
    ServerSSM - Server Segmentation State Machine
    """

    def __init__(self, sap, remoteDevice):
        SSM.__init__(self, sap, remoteDevice)

    def set_state(self, new_state, timer=0):
        """This function is called when the client wants to change state."""
        # do the regular state change
        SSM.set_state(self, new_state, timer)
        # when completed or aborted, remove tracking
        if (new_state == COMPLETED) or (new_state == ABORTED):
            # remove from active transactions
            self.ssmSAP.serverTransactions.remove(self)
            # release device information
            self.ssmSAP.deviceInfoCache.release_device_info(self.remoteDevice)

    def request(self, apdu):
        """
        This function is called by transaction functions to send to the application.
        """
        # make sure it has a good source and destination
        apdu.pduSource = self.remoteDevice.address
        apdu.pduDestination = None
        # send it via the device
        self.ssmSAP.sap_request(apdu)

    def indication(self, apdu):
        """
        This function is called for each downstream packet related to the transaction.
        """
        if self.state == IDLE:
            self.idle(apdu)
        elif self.state == SEGMENTED_REQUEST:
            self.segmented_request(apdu)
        elif self.state == AWAIT_RESPONSE:
            self.await_response(apdu)
        elif self.state == SEGMENTED_RESPONSE:
            self.segmented_response(apdu)
        else:
            # invalid state
            pass

    def response(self, apdu):
        """
        This function is called by transaction functions when they want to send a message to the device.
        """
        # make sure it has a good source and destination
        apdu.pduSource = None
        apdu.pduDestination = self.remoteDevice.address
        # send it via the device
        self.ssmSAP.request(apdu)

    def confirmation(self, apdu):
        """
        This function is called when the application has provided a response and needs it to be sent to the client.
        """
        # check to see we are in the correct state
        if self.state != AWAIT_RESPONSE:
            # not expecting a response
            pass
        # abort response
        if apdu.apduType == AbortPDU.pduType:
            self.set_state(ABORTED)
            # send the response to the device
            self.response(apdu)
            return
        # simple response
        if (apdu.apduType == SimpleAckPDU.pduType) or (apdu.apduType == ErrorPDU.pduType) or (
                apdu.apduType == RejectPDU.pduType):
            # simple ack, error, or reject
            # transaction completed
            self.set_state(COMPLETED)
            # send the response to the device
            self.response(apdu)
            return
        # complex ack
        if apdu.apduType == ComplexAckPDU.pduType:
            # save the response and set the segmentation context
            self.set_segmentation_context(apdu)
            # the segment size is the minimum of the maximum size I can transmit
            # (assumed to have no local buffer limitations), the maximum conveyable
            # by the internetwork to the remote device, and the maximum APDU size
            # accepted by the remote device.
            self.segmentSize = min(self.remoteDevice.maxNpduLength, self.remoteDevice.maxApduLengthAccepted)
            # compute the segment count
            # ToDo: minus the header?
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
                # segmentation required
                # make sure we support segmented transmit
                if self.ssmSAP.segmentationSupported not in ('segmentedTransmit', 'segmentedBoth'):
                    # server can't send segmented responses
                    abort = self.abort(AbortReason.segmentationNotSupported)
                    self.response(abort)
                    return
                # make sure client supports segmented receive
                if self.remoteDevice.segmentationSupported not in ('segmentedReceive', 'segmentedBoth'):
                    # client can't receive segmented responses
                    abort = self.abort(AbortReason.segmentationNotSupported)
                    self.response(abort)
                    return
            # ToDo: check for APDUTooLong?
            # initialize the state
            self.segmentRetryCount = 0
            self.initialSequenceNumber = 0
            self.proposedWindowSize = self.ssmSAP.maxSegmentsAccepted
            self.actualWindowSize = 1

            # send out the first segment (or the whole thing)
            if self.segmentCount == 1:
                self.response(apdu)
                self.set_state(COMPLETED)
            else:
                self.response(self.get_segment(0))
                self.set_state(SEGMENTED_RESPONSE, self.ssmSAP.segmentTimeout)
        else:
            raise RuntimeError('invalid APDU (4)')

    def handle_timeout(self):
        """
        This function is called when the client has failed to send all of the segments of a segmented request,
        the application has taken too long to complete the request, or the client failed to ack the segments of a
        segmented response.
        """
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
            raise RuntimeError('invalid state')

    def abort(self, reason):
        """
        This function is called when the application would like to abort the transaction.
        There is no notification back to the application.
        """
        # change the state to aborted
        self.set_state(ABORTED)
        # return an abort APDU
        return AbortPDU(True, self.invokeID, reason)

    def idle(self, apdu):
        # make sure we're getting confirmed requests
        if not isinstance(apdu, ConfirmedRequestPDU):
            raise RuntimeError('invalid APDU (5)')
        # save the invoke ID
        self.invokeID = apdu.apduInvokeID
        # make sure the device information is synced with the request
        if apdu.apduSA:
            if self.remoteDevice.segmentationSupported == 'noSegmentation':
                # client actually supports segmented receive
                self.remoteDevice.segmentationSupported = 'segmentedReceive'
                # tell the cache the info has been updated
                self.ssmSAP.deviceInfoCache.update_device_info(self.remoteDevice)
            elif self.remoteDevice.segmentationSupported == 'segmentedTransmit':
                # client actually supports both segmented transmit and receive
                self.remoteDevice.segmentationSupported = 'segmentedBoth'
                # tell the cache the info has been updated
                self.ssmSAP.deviceInfoCache.update_device_info(self.remoteDevice)
            elif self.remoteDevice.segmentationSupported == 'segmentedReceive':
                pass

            elif self.remoteDevice.segmentationSupported == 'segmentedBoth':
                pass
            else:
                raise RuntimeError("invalid segmentation supported in device info")

        if apdu.apduMaxSegs != self.remoteDevice.maxSegmentsAccepted:
            # update maximum segments accepted?
            pass
        if apdu.apduMaxResp != self.remoteDevice.maxApduLengthAccepted:
            # update maximum max APDU length accepted?
            pass

        # save the number of segments the client is willing to accept in the ack
        self.maxSegmentsAccepted = apdu.apduMaxSegs
        # unsegmented request
        if not apdu.apduSeg:
            self.set_state(AWAIT_RESPONSE, self.ssmSAP.applicationTimeout)
            self.request(apdu)
            return
        # make sure we support segmented requests
        if self.ssmSAP.segmentationSupported not in ('segmentedReceive', 'segmentedBoth'):
            abort = self.abort(AbortReason.segmentationNotSupported)
            self.response(abort)
            return
        # save the request and set the segmentation context
        self.set_segmentation_context(apdu)
        # the window size is the minimum of what I'm willing to receive and
        # what the device has said it would like to send
        self.actualWindowSize = min(apdu.apduWin, self.ssmSAP.maxSegmentsAccepted)
        # initialize the state
        self.lastSequenceNumber = 0
        self.initialSequenceNumber = 0
        self.set_state(SEGMENTED_REQUEST, self.ssmSAP.segmentTimeout)
        # send back a segment ack
        segack = SegmentAckPDU(0, 1, self.invokeID, self.initialSequenceNumber, self.actualWindowSize)
        self.response(segack)

    def segmented_request(self, apdu):
        # some kind of problem
        if apdu.apduType == AbortPDU.pduType:
            self.set_state(COMPLETED)
            self.response(apdu)
            return
        # the only messages we should be getting are confirmed requests
        elif apdu.apduType != ConfirmedRequestPDU.pduType:
            abort = self.abort(AbortReason.invalidApduInThisState)
            self.request(abort)
            self.response(abort)
            return
        # it must be segmented
        elif not apdu.apduSeg:
            abort = self.abort(AbortReason.invalidApduInThisState)
            self.request(abort)
            self.response(abort)
            return
        # proper segment number
        if apdu.apduSeq != (self.lastSequenceNumber + 1) % 256:
            # segment received out of order
            self.restart_timer(self.ssmSAP.segmentTimeout)
            # send back a segment ack
            seg_ack = SegmentAckPDU(1, 1, self.invokeID, self.initialSequenceNumber, self.actualWindowSize)
            self.response(seg_ack)
            return
        # add the data
        self.append_segment(apdu)
        # update the sequence number
        self.lastSequenceNumber = (self.lastSequenceNumber + 1) % 256
        # last segment?
        if not apdu.apduMor:
            # no more follows
            # send back a final segment ack
            seg_ack = SegmentAckPDU(0, 1, self.invokeID, self.lastSequenceNumber, self.actualWindowSize)
            self.response(seg_ack)
            # forward the whole thing to the application
            self.set_state(AWAIT_RESPONSE, self.ssmSAP.applicationTimeout)
            self.request(self.segmentAPDU)

        elif apdu.apduSeq == ((self.initialSequenceNumber + self.actualWindowSize) % 256):
            # last segment in the group
            self.initialSequenceNumber = self.lastSequenceNumber
            self.restart_timer(self.ssmSAP.segmentTimeout)
            # send back a segment ack
            seg_ack = SegmentAckPDU(0, 1, self.invokeID, self.initialSequenceNumber, self.actualWindowSize)
            self.response(seg_ack)
        else:
            # wait for more segments
            self.restart_timer(self.ssmSAP.segmentTimeout)

    def segmented_request_timeout(self):
        # give up
        self.set_state(ABORTED)

    def await_response(self, apdu):
        if isinstance(apdu, ConfirmedRequestPDU):
            # client is trying this request again
            pass
        elif isinstance(apdu, AbortPDU):
            # client aborting this request
            # forward abort to the application
            self.set_state(ABORTED)
            self.request(apdu)
        else:
            raise RuntimeError('invalid APDU (6)')

    def await_response_timeout(self):
        """
        This function is called when the application has taken too long to respond to a clients request.
        The client has probably long since given up.
        """
        abort = self.abort(AbortReason.serverTimeout)
        self.request(abort)

    def segmented_response(self, apdu):
        # client is ready for the next segment
        if (apdu.apduType == SegmentAckPDU.pduType):
            # segment ack
            # duplicate ack received?
            if not self.in_window(apdu.apduSeq, self.initialSequenceNumber):
                # not in window
                self.restart_timer(self.ssmSAP.segmentTimeout)
            # final ack received?
            elif self.sentAllSegments:
                # all done sending response
                self.set_state(COMPLETED)
            else:
                # more segments to send
                self.initialSequenceNumber = (apdu.apduSeq + 1) % 256
                self.actualWindowSize = apdu.apduWin
                self.segmentRetryCount = 0
                self.FillWindow(self.initialSequenceNumber)
                self.restart_timer(self.ssmSAP.segmentTimeout)
        # some kind of problem
        elif apdu.apduType == AbortPDU.pduType:
            self.set_state(COMPLETED)
            self.response(apdu)
        else:
            raise RuntimeError('invalid APDU (7)')

    def segmented_response_timeout(self):
        # try again
        if self.segmentRetryCount < self.ssmSAP.retryCount:
            self.segmentRetryCount += 1
            self.start_timer(self.ssmSAP.segmentTimeout)
            self.FillWindow(self.initialSequenceNumber)
        else:
            # give up
            self.set_state(ABORTED)
