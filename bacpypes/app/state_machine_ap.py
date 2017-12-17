import logging
from ..comm import Client, ServiceAccessPoint
from ..link import Address
from ..apdu import AbortPDU, ComplexAckPDU, ConfirmedRequestPDU, ErrorPDU, RejectPDU, SegmentAckPDU, \
    SimpleAckPDU, UnconfirmedRequestPDU, apdu_types
from .client_ssm import ClientSSM
from .server_ssm import ServerSSM

_logger = logging.getLogger(__name__)
__all__ = ['StateMachineAccessPoint']


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
            _logger.warning('    - unknown apduType: %r', pdu.apduType)
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
                _logger.warning('%s is not a local or remote station', apdu.pduDestination)
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
