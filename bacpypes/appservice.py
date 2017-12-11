#!/usr/bin/python

"""
Application Layer
"""

import logging
from .debugging import DebugContents, bacpypes_debugging
from .comm import Client, ServiceAccessPoint, ApplicationServiceElement
from .task import OneShotTask
from .pdu import Address
from .apdu import AbortPDU, AbortReason, ComplexAckPDU, \
    ConfirmedRequestPDU, Error, ErrorPDU, RejectPDU, SegmentAckPDU, \
    SimpleAckPDU, UnconfirmedRequestPDU, apdu_types, \
    unconfirmed_request_types, confirmed_request_types, complex_ack_types, \
    error_types
from .errors import RejectException, AbortException

_logger = logging.getLogger(__name__)

# transaction states
IDLE = 0
SEGMENTED_REQUEST = 1
AWAIT_CONFIRMATION = 2
AWAIT_RESPONSE = 3
SEGMENTED_RESPONSE = 4
SEGMENTED_CONFIRMATION = 5
COMPLETED = 6
ABORTED = 7


class SSM(OneShotTask, DebugContents):
    """
    SSM - Segmentation State Machine
    """
    transactionLabels = [
        'IDLE', 'SEGMENTED_REQUEST', 'AWAIT_CONFIRMATION', 'AWAIT_RESPONSE',
        'SEGMENTED_RESPONSE', 'SEGMENTED_CONFIRMATION', 'COMPLETED', 'ABORTED'
    ]

    def __init__(self, sap, remote_device):
        """Common parts for client and server segmentation."""
        OneShotTask.__init__(self)
        self.ssmSAP = sap  # service access point
        self.remoteDevice = remote_device  # remote device information, a DeviceInfo instance
        self.invokeID = None  # invoke ID
        self.state = IDLE  # initial state
        self.segmentAPDU = None  # refers to request or response
        self.segmentSize = None  # how big the pieces are
        self.segmentCount = None
        self.retryCount = None
        self.segmentRetryCount = None
        self.sentAllSegments = None
        self.lastSequenceNumber = None
        self.initialSequenceNumber = None
        self.actualWindowSize = None
        self.proposedWindowSize = None
        # the maximum number of segments starts out being what's in the SAP
        # which is the defaults or values from the local device.
        self.maxSegmentsAccepted = self.ssmSAP.maxSegmentsAccepted

    def start_timer(self, msecs):
        # if this is active, pull it
        if self.isScheduled:
            self.suspend_task()
        # now install this
        self.install_task(delta=msecs / 1000.0)

    def stop_timer(self):
        # if this is active, pull it
        if self.isScheduled:
            self.suspend_task()

    def restart_timer(self, msecs):
        # if this is active, pull it
        if self.isScheduled:
            self.suspend_task()

        # now install this
        self.install_task(delta=msecs / 1000.0)

    def set_state(self, new_state, timer=0):
        """This function is called when the derived class wants to change state."""
        # make sure we have a correct transition
        if (self.state == COMPLETED) or (self.state == ABORTED):
            e = RuntimeError(
                f'invalid state transition from {SSM.transactionLabels[self.state]} to {SSM.transactionLabels[new_state]}')
            _logger.exception(e)
            raise e
        # stop any current timer
        self.stop_timer()
        # make the change
        self.state = new_state

        # if another timer should be started, start it
        if timer:
            self.start_timer(timer)

    def set_segmentation_context(self, apdu):
        """This function is called to set the segmentation context."""
        # set the context
        self.segmentAPDU = apdu

    def get_segment(self, indx):
        """
        This function returns an APDU coorisponding to a particular segment of a confirmed request or complex ack.
        The segmentAPDU is the context.
        """
        # check for no context
        if not self.segmentAPDU:
            raise RuntimeError('no segmentation context established')
        # check for invalid segment number
        if indx >= self.segmentCount:
            raise RuntimeError(f'invalid segment number {indx}, APDU has {self.segmentCount} segments')

        if self.segmentAPDU.apduType == ConfirmedRequestPDU.pduType:
            seg_apdu = ConfirmedRequestPDU(self.segmentAPDU.apduService)
            seg_apdu.apduMaxSegs = self.maxSegmentsAccepted
            seg_apdu.apduMaxResp = self.ssmSAP.maxApduLengthAccepted
            seg_apdu.apduInvokeID = self.invokeID
            # segmented response accepted?
            seg_apdu.apduSA = self.ssmSAP.segmentationSupported in ('segmentedReceive', 'segmentedBoth')
        elif self.segmentAPDU.apduType == ComplexAckPDU.pduType:
            seg_apdu = ComplexAckPDU(self.segmentAPDU.apduService, self.segmentAPDU.apduInvokeID)
        else:
            raise RuntimeError('invalid APDU type for segmentation context')
        # maintain the the user data reference
        seg_apdu.pduUserData = self.segmentAPDU.pduUserData
        # make sure the destination is set
        seg_apdu.pduDestination = self.remoteDevice.address
        # segmented message?
        if self.segmentCount != 1:
            seg_apdu.apduSeg = True
            seg_apdu.apduMor = (indx < (self.segmentCount - 1))  # more follows
            seg_apdu.apduSeq = indx % 256  # sequence number
            seg_apdu.apduWin = self.proposedWindowSize  # window size
        else:
            seg_apdu.apduSeg = False
            seg_apdu.apduMor = False
        # add the content
        offset = indx * self.segmentSize
        seg_apdu.put_data(self.segmentAPDU.pduData[offset:offset + self.segmentSize])
        # success
        return seg_apdu

    def append_segment(self, apdu):
        """
        This function appends the apdu content to the end of the current APDU being built.
        The segmentAPDU is the context.
        """
        # check for no context
        if not self.segmentAPDU:
            raise RuntimeError('no segmentation context established')
        # append the data
        self.segmentAPDU.put_data(apdu.pduData)

    def in_window(self, seqA, seqB):
        rslt = ((seqA - seqB + 256) % 256) < self.actualWindowSize
        return rslt

    def FillWindow(self, seqNum):
        """
        This function sends all of the packets necessary to fill out the segmentation window.
        """
        for ix in range(self.actualWindowSize):
            apdu = self.get_segment(seqNum + ix)
            # send the message
            self.ssmSAP.request(apdu)
            # check for no more follows
            if not apdu.apduMor:
                self.sentAllSegments = True
                break


class ClientSSM(SSM):
    """
    ClientSSM - Client Segmentation State Machine
    """

    def __init__(self, sap, remote_device):
        super(ClientSSM, self).__init__(sap, remote_device)
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

    def process_task(self):
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


class ServerSSM(SSM):
    """
    ServerSSM - Server Segmentation State Machine
    """

    def __init__(self, sap, remote_device):
        super(SSM, self).__init__(sap, remote_device)

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

    def process_task(self):
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


@bacpypes_debugging
class StateMachineAccessPoint(Client, ServiceAccessPoint):
    """
    StateMachineAccessPoint
    """
    def __init__(self, local_device=None, device_info_cache=None, sap=None, cid=None):
        # basic initialization
        Client.__init__(self, cid)
        ServiceAccessPoint.__init__(self, sap)
        # save a reference to the device information cache
        self.deviceInfoCache = device_info_cache
        # client settings
        self.nextInvokeID = 1
        self.clientTransactions = []
        # server settings
        self.serverTransactions = []
        # confirmed request defaults
        self.retryCount = 3
        self.retryTimeout = 3000
        self.maxApduLengthAccepted = 1024
        # segmentation defaults
        self.segmentationSupported = 'noSegmentation'
        self.segmentTimeout = 1500
        self.maxSegmentsAccepted = 8
        # device communication control
        self.dccEnableDisable = 'enable'
        # local device object provides these
        if local_device:
            self.retryCount = local_device.numberOfApduRetries
            self.retryTimeout = local_device.apduTimeout
            self.segmentationSupported = local_device.segmentationSupported
            self.segmentTimeout = local_device.apduSegmentTimeout
            self.maxSegmentsAccepted = local_device.maxSegmentsAccepted
            self.maxApduLengthAccepted = local_device.maxApduLengthAccepted
        # how long the state machine is willing to wait for the application
        # layer to form a response and send it
        self.applicationTimeout = 3000

    def get_next_invoke_id(self, addr):
        """Called by clients to get an unused invoke ID."""
        initial_id = self.nextInvokeID
        while True:
            invoke_id = self.nextInvokeID
            self.nextInvokeID = (self.nextInvokeID + 1) % 256
            # see if we've checked for them all
            if initial_id == self.nextInvokeID:
                raise RuntimeError('no available invoke ID')
            for tr in self.clientTransactions:
                if (invoke_id == tr.invokeID) and (addr == tr.remoteDevice.address):
                    break
            else:
                break
        return invoke_id

    def confirmation(self, pdu):
        """Packets coming up the stack are APDU's."""
        # check device communication control
        if self.dccEnableDisable == 'enable':
            # communications enabled
            pass
        elif self.dccEnableDisable == 'disable':
            if (pdu.apduType == 0) and (pdu.apduService == 17):
                # continue with DCC request
                pass
            elif (pdu.apduType == 0) and (pdu.apduService == 20):
                # continue with reinitialize device
                pass
            elif (pdu.apduType == 1) and (pdu.apduService == 8):
                # continue with Who-Is
                pass
            else:
                # not a Who-Is, dropped
                return
        elif self.dccEnableDisable == 'disableInitiation':
            # initiation disabled
            pass
        # make a more focused interpretation
        atype = apdu_types.get(pdu.apduType)
        if not atype:
            _logger.warning(f'    - unknown apduType: {pdu.apduType!r}')
            return
        # decode it
        apdu = atype()
        apdu.decode(pdu)
        if isinstance(apdu, ConfirmedRequestPDU):
            # find duplicates of this request
            for tr in self.serverTransactions:
                if (apdu.pduSource == tr.remoteDevice.address) and (apdu.apduInvokeID == tr.invokeID):
                    break
            else:
                # find the remote device information
                remote_device = self.deviceInfoCache.get_device_info(apdu.pduSource)
                # build a server transaction
                tr = ServerSSM(self, remote_device)
                # add it to our transactions to track it
                self.serverTransactions.append(tr)
            # let it run with the apdu
            tr.indication(apdu)
        elif isinstance(apdu, UnconfirmedRequestPDU):
            # deliver directly to the application
            self.sap_request(apdu)
        elif isinstance(apdu, SimpleAckPDU) \
                or isinstance(apdu, ComplexAckPDU) \
                or isinstance(apdu, ErrorPDU) \
                or isinstance(apdu, RejectPDU):
            # find the client transaction this is acking
            for tr in self.clientTransactions:
                if (apdu.apduInvokeID == tr.invokeID) and (apdu.pduSource == tr.remoteDevice.address):
                    break
            else:
                return
            # send the packet on to the transaction
            tr.confirmation(apdu)
        elif isinstance(apdu, AbortPDU):
            # find the transaction being aborted
            if apdu.apduSrv:
                for tr in self.clientTransactions:
                    if (apdu.apduInvokeID == tr.invokeID) and (apdu.pduSource == tr.remoteDevice.address):
                        break
                else:
                    return
                # send the packet on to the transaction
                tr.confirmation(apdu)
            else:
                for tr in self.serverTransactions:
                    if (apdu.apduInvokeID == tr.invokeID) and (apdu.pduSource == tr.remoteDevice.address):
                        break
                else:
                    return
                # send the packet on to the transaction
                tr.indication(apdu)
        elif isinstance(apdu, SegmentAckPDU):
            # find the transaction being aborted
            if apdu.apduSrv:
                for tr in self.clientTransactions:
                    if (apdu.apduInvokeID == tr.invokeID) and (apdu.pduSource == tr.remoteDevice.address):
                        break
                else:
                    return
                # send the packet on to the transaction
                tr.confirmation(apdu)
            else:
                for tr in self.serverTransactions:
                    if (apdu.apduInvokeID == tr.invokeID) and (apdu.pduSource == tr.remoteDevice.address):
                        break
                else:
                    return

                # send the packet on to the transaction
                tr.indication(apdu)
        else:
            raise RuntimeError("invalid APDU (8)")

    def sap_indication(self, apdu):
        """
        This function is called when the application is requesting a new transaction as a client.
        """
        # check device communication control
        if self.dccEnableDisable == 'enable':
            # communications enabled
            pass
        elif self.dccEnableDisable == 'disable':
            # communications disabled
            return
        elif self.dccEnableDisable == 'disableInitiation':
            # initiation disabled
            if (apdu.apduType == 1) and (apdu.apduService == 0):
                # continue with I-Am
                pass
            else:
                # not an I-Am
                return
        if isinstance(apdu, UnconfirmedRequestPDU):
            # deliver to the device
            self.request(apdu)
        elif isinstance(apdu, ConfirmedRequestPDU):
            # make sure it has an invoke ID
            if apdu.apduInvokeID is None:
                apdu.apduInvokeID = self.get_next_invoke_id(apdu.pduDestination)
            else:
                # verify the invoke ID isn't already being used
                for tr in self.clientTransactions:
                    if (apdu.apduInvokeID == tr.invokeID) and (apdu.pduDestination == tr.remoteDevice.address):
                        raise RuntimeError('invoke ID in use')
            # warning for bogus requests
            if (apdu.pduDestination.addrType != Address.localStationAddr) and (
                    apdu.pduDestination.addrType != Address.remoteStationAddr):
                _logger.warning(f'{apdu.pduDestination} is not a local or remote station')
            # find the remote device information
            remote_device = self.deviceInfoCache.get_device_info(apdu.pduDestination)
            # create a client transaction state machine
            tr = ClientSSM(self, remote_device)
            # add it to our transactions to track it
            self.clientTransactions.append(tr)
            # let it run
            tr.indication(apdu)

        else:
            raise RuntimeError('invalid APDU (9)')

    def sap_confirmation(self, apdu):
        """
        This function is called when the application is responding to a request,
        the apdu may be a simple ack, complex ack, error, reject or abort.
        """
        if isinstance(apdu, SimpleAckPDU) \
                or isinstance(apdu, ComplexAckPDU) \
                or isinstance(apdu, ErrorPDU) \
                or isinstance(apdu, RejectPDU) \
                or isinstance(apdu, AbortPDU):
            # find the appropriate server transaction
            for tr in self.serverTransactions:
                if (apdu.apduInvokeID == tr.invokeID) and (apdu.pduDestination == tr.remoteDevice.address):
                    break
            else:
                return
            # pass control to the transaction
            tr.confirmation(apdu)
        else:
            raise RuntimeError('invalid APDU (10)')


@bacpypes_debugging
class ApplicationServiceAccessPoint(ApplicationServiceElement, ServiceAccessPoint):
    """
    ApplicationServiceAccessPoint
    """
    def __init__(self, aseID=None, sapID=None):
        ApplicationServiceElement.__init__(self, aseID)
        ServiceAccessPoint.__init__(self, sapID)

    def indication(self, apdu):
        if isinstance(apdu, ConfirmedRequestPDU):
            atype = confirmed_request_types.get(apdu.apduService)
            if not atype:
                # no confirmed request decoder
                return
            # assume no errors found
            error_found = None
            try:
                xpdu = atype()
                xpdu.decode(apdu)
            except RejectException as err:
                # decoding reject
                error_found = err
            except AbortException as err:
                # decoding abort
                error_found = err
            # no error so far, keep going
            if not error_found:
                # no decoding error
                try:
                    # forward the decoded packet
                    self.sap_request(xpdu)
                except RejectException as err:
                    # execution reject
                    error_found = err
                except AbortException as err:
                    # execution abort
                    error_found = err

            # if there was an error, send it back to the client
            if isinstance(error_found, RejectException):
                # reject exception
                reject_pdu = RejectPDU(reason=error_found.rejectReason)
                reject_pdu.set_context(apdu)
                # send it to the client
                self.response(reject_pdu)
            elif isinstance(error_found, AbortException):
                # abort exception
                abort_pdu = AbortPDU(reason=error_found.abortReason)
                abort_pdu.set_context(apdu)
                # send it to the client
                self.response(abort_pdu)

        elif isinstance(apdu, UnconfirmedRequestPDU):
            atype = unconfirmed_request_types.get(apdu.apduService)
            if not atype:
                # no unconfirmed request decoder
                return
            try:
                xpdu = atype()
                xpdu.decode(apdu)
            except RejectException as err:
                # decoding reject
                return
            except AbortException as err:
                # decoding abort
                return
            try:
                # forward the decoded packet
                self.sap_request(xpdu)
            except RejectException as err:
                # execution reject
                pass
            except AbortException as err:
                # execution abort
                pass

        else:
            # unknown PDU type?!
            pass

    def sap_indication(self, apdu):
        if isinstance(apdu, ConfirmedRequestPDU):
            try:
                xpdu = ConfirmedRequestPDU()
                apdu.encode(xpdu)
                apdu._xpdu = xpdu
            except Exception as err:
                _logger.exception(f'confirmed request encoding error: {err!r}')
                return

        elif isinstance(apdu, UnconfirmedRequestPDU):
            try:
                xpdu = UnconfirmedRequestPDU()
                apdu.encode(xpdu)
                apdu._xpdu = xpdu
            except Exception as err:
                _logger.exception(f'unconfirmed request encoding error: {err!r}')
                return

        else:
            # unknown PDU type?!
            return
        # forward the encoded packet
        self.request(xpdu)
        # if the upper layers of the application did not assign an invoke ID,
        # copy the one that was assigned on its way down the stack
        if isinstance(apdu, ConfirmedRequestPDU) and apdu.apduInvokeID is None:
            # pass invoke ID upstream
            apdu.apduInvokeID = xpdu.apduInvokeID

    def confirmation(self, apdu):
        if isinstance(apdu, SimpleAckPDU):
            xpdu = apdu

        elif isinstance(apdu, ComplexAckPDU):
            atype = complex_ack_types.get(apdu.apduService)
            if not atype:
                # no complex ack decoder
                return
            try:
                xpdu = atype()
                xpdu.decode(apdu)
            except Exception as err:
                # unconfirmed request decoding error
                return

        elif isinstance(apdu, ErrorPDU):
            atype = error_types.get(apdu.apduService)
            if not atype:
                # no special error decoder
                atype = Error
            try:
                xpdu = atype()
                xpdu.decode(apdu)
            except Exception as err:
                _logger.exception(f'error PDU decoding error: {err!r}')
                xpdu = Error(errorClass=0, errorCode=0)
        elif isinstance(apdu, RejectPDU):
            xpdu = apdu
        elif isinstance(apdu, AbortPDU):
            xpdu = apdu
        else:
            # unknown PDU type
            return
        # forward the decoded packet
        self.sap_response(xpdu)

    def sap_confirmation(self, apdu):
        if isinstance(apdu, SimpleAckPDU):
            xpdu = apdu
        elif isinstance(apdu, ComplexAckPDU):
            xpdu = ComplexAckPDU()
            apdu.encode(xpdu)
        elif isinstance(apdu, ErrorPDU):
            xpdu = ErrorPDU()
            apdu.encode(xpdu)
        elif isinstance(apdu, RejectPDU):
            xpdu = apdu
        elif isinstance(apdu, AbortPDU):
            xpdu = apdu
        else:
            # unknown PDU type
            return
        # forward the encoded packet
        self.response(xpdu)
