
import logging
from ..debugging import DebugContents
from ..task import call_later
from ..apdu import ComplexAckPDU, ConfirmedRequestPDU
from .ssm_states import *

_logger = logging.getLogger(__name__)
__all__ = ['SSM']


class SSM(DebugContents):
    """
    SSM - Segmentation State Machine
    """
    transactionLabels = [
        'IDLE', 'SEGMENTED_REQUEST', 'AWAIT_CONFIRMATION', 'AWAIT_RESPONSE',
        'SEGMENTED_RESPONSE', 'SEGMENTED_CONFIRMATION', 'COMPLETED', 'ABORTED'
    ]

    def __init__(self, sap, remote_device):
        """Common parts for client and server segmentation."""
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
        self.timer_handle = None

    def start_timer(self, msecs):
        # if this is active, pull it
        if self.timer_handle:
            self.timer_handle.cancel()
        # now install this
        self.timer_handle = call_later(msecs / 1000.0, self.handle_timeout)

    def stop_timer(self):
        # if this is active, pull it
        if self.timer_handle:
            self.timer_handle.cancel()
            self.timer_handle = None

    def restart_timer(self, msecs):
        # if this is active, pull it
        self.start_timer(msecs)

    def handle_timeout(self):
        raise NotImplementedError()

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
