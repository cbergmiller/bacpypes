import logging
from ..errors import DecodingError
from ..debugging import DebugContents, btox
from ..link import Address, PCI, GlobalBroadcast, RemoteBroadcast, RemoteStation

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['NPCI']


class NPCI(PCI, DebugContents):
    _debug_contents = ('npduVersion', 'npduControl', 'npduDADR', 'npduSADR', 'npduHopCount', 'npduNetMessage',
                       'npduVendorID')

    whoIsRouterToNetwork = 0x00
    iAmRouterToNetwork = 0x01
    iCouldBeRouterToNetwork = 0x02
    rejectMessageToNetwork = 0x03
    routerBusyToNetwork = 0x04
    routerAvailableToNetwork = 0x05
    initializeRoutingTable = 0x06
    initializeRoutingTableAck = 0x07
    establishConnectionToNetwork = 0x08
    disconnectConnectionToNetwork = 0x09
    challengeRequest = 0x0A
    securityPayload = 0x0B
    securityResponse = 0x0C
    requestKeyUpdate = 0x0D
    updateKeySet = 0x0E
    updateDistributionKey = 0x0F
    requestMasterKey = 0x10
    setMasterKey = 0x11
    whatIsNetworkNumber = 0x12
    networkNumberIs = 0x13

    def __init__(self, *args, **kwargs):
        super(NPCI, self).__init__(*args, **kwargs)
        self.npduVersion = 1
        self.npduControl = None
        self.npduDADR = None
        self.npduSADR = None
        self.npduHopCount = None
        self.npduNetMessage = None
        self.npduVendorID = None

    def update(self, npci):
        PCI.update(self, npci)
        self.npduVersion = npci.npduVersion
        self.npduControl = npci.npduControl
        self.npduDADR = npci.npduDADR
        self.npduSADR = npci.npduSADR
        self.npduHopCount = npci.npduHopCount
        self.npduNetMessage = npci.npduNetMessage
        self.npduVendorID = npci.npduVendorID

    def encode(self, pdu):
        """encode the contents of the NPCI into the PDU."""
        if DEBUG: _logger.debug("encode %s", repr(pdu))
        PCI.update(pdu, self)
        # only version 1 messages supported
        pdu.put(self.npduVersion)
        # build the flags
        if self.npduNetMessage is not None:
            netLayerMessage = 0x80
        else:
            netLayerMessage = 0x00
        # map the destination address
        dnetPresent = 0x00
        if self.npduDADR is not None:
            dnetPresent = 0x20
        # map the source address
        snetPresent = 0x00
        if self.npduSADR is not None:
            snetPresent = 0x08
        # encode the control octet
        control = netLayerMessage | dnetPresent | snetPresent
        if self.pduExpectingReply:
            control |= 0x04
        control |= (self.pduNetworkPriority & 0x03)
        self.npduControl = control
        pdu.put(control)
        # make sure expecting reply and priority get passed down
        pdu.pduExpectingReply = self.pduExpectingReply
        pdu.pduNetworkPriority = self.pduNetworkPriority
        # encode the destination address
        if dnetPresent:
            if self.npduDADR.addrType == Address.remoteStationAddr:
                pdu.put_short(self.npduDADR.addrNet)
                pdu.put(self.npduDADR.addrLen)
                pdu.put_data(self.npduDADR.addrAddr)
            elif self.npduDADR.addrType == Address.remoteBroadcastAddr:
                pdu.put_short(self.npduDADR.addrNet)
                pdu.put(0)
            elif self.npduDADR.addrType == Address.globalBroadcastAddr:
                pdu.put_short(0xFFFF)
                pdu.put(0)
        # encode the source address
        if snetPresent:
            pdu.put_short(self.npduSADR.addrNet)
            pdu.put(self.npduSADR.addrLen)
            pdu.put_data(self.npduSADR.addrAddr)
        # put the hop count
        if dnetPresent:
            pdu.put(self.npduHopCount)
        # put the network layer message type (if present)
        if netLayerMessage:
            pdu.put(self.npduNetMessage)
            # put the vendor ID
            if (self.npduNetMessage >= 0x80) and (self.npduNetMessage <= 0xFF):
                pdu.put_short(self.npduVendorID)

    def decode(self, pdu):
        """decode the contents of the PDU and put them into the NPDU."""
        if DEBUG: _logger.debug("decode %s", str(pdu))
        PCI.update(self, pdu)
        # check the length
        if len(pdu.pduData) < 2:
            raise DecodingError("invalid length")
        # only version 1 messages supported
        self.npduVersion = pdu.get()
        if (self.npduVersion != 0x01):
            raise DecodingError("only version 1 messages supported")
        # decode the control octet
        self.npduControl = control = pdu.get()
        netLayerMessage = control & 0x80
        dnetPresent = control & 0x20
        snetPresent = control & 0x08
        self.pduExpectingReply = (control & 0x04) != 0
        self.pduNetworkPriority = control & 0x03
        # extract the destination address
        if dnetPresent:
            dnet = pdu.get_short()
            dlen = pdu.get()
            dadr = pdu.get_data(dlen)
            if dnet == 0xFFFF:
                self.npduDADR = GlobalBroadcast()
            elif dlen == 0:
                self.npduDADR = RemoteBroadcast(dnet)
            else:
                self.npduDADR = RemoteStation(dnet, dadr)
        # extract the source address
        if snetPresent:
            snet = pdu.get_short()
            slen = pdu.get()
            sadr = pdu.get_data(slen)
            if snet == 0xFFFF:
                raise DecodingError("SADR can't be a global broadcast")
            elif slen == 0:
                raise DecodingError("SADR can't be a remote broadcast")
            self.npduSADR = RemoteStation(snet, sadr)
        # extract the hop count
        if dnetPresent:
            self.npduHopCount = pdu.get()
        # extract the network layer message type (if present)
        if netLayerMessage:
            self.npduNetMessage = pdu.get()
            if (self.npduNetMessage >= 0x80) and (self.npduNetMessage <= 0xFF):
                # extract the vendor ID
                self.npduVendorID = pdu.get_short()
        else:
            # application layer message
            self.npduNetMessage = None

    def npci_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if DEBUG: _logger.debug("npci_contents use_dict=%r as_class=%r", use_dict, as_class)
        # make/extend the dictionary of content
        if use_dict is None:
            if DEBUG: _logger.debug("    - new use_dict")
            use_dict = as_class()
        # version and control are simple
        use_dict.__setitem__('version', self.npduVersion)
        use_dict.__setitem__('control', self.npduControl)
        # dnet/dlen/dadr
        if self.npduDADR is not None:
            if self.npduDADR.addrType == Address.remoteStationAddr:
                use_dict.__setitem__('dnet', self.npduDADR.addrNet)
                use_dict.__setitem__('dlen', self.npduDADR.addrLen)
                use_dict.__setitem__('dadr', btox(self.npduDADR.addrAddr or b''))
            elif self.npduDADR.addrType == Address.remoteBroadcastAddr:
                use_dict.__setitem__('dnet', self.npduDADR.addrNet)
                use_dict.__setitem__('dlen', 0)
                use_dict.__setitem__('dadr', '')
            elif self.npduDADR.addrType == Address.globalBroadcastAddr:
                use_dict.__setitem__('dnet', 0xFFFF)
                use_dict.__setitem__('dlen', 0)
                use_dict.__setitem__('dadr', '')
        # snet/slen/sadr
        if self.npduSADR is not None:
            use_dict.__setitem__('snet', self.npduSADR.addrNet)
            use_dict.__setitem__('slen', self.npduSADR.addrLen)
            use_dict.__setitem__('sadr', btox(self.npduSADR.addrAddr or b''))
        # hop count
        if self.npduHopCount is not None:
            use_dict.__setitem__('hop_count', self.npduHopCount)
        # network layer message name decoded
        if self.npduNetMessage is not None:
            use_dict.__setitem__('net_message', self.npduNetMessage)
        if self.npduVendorID is not None:
            use_dict.__setitem__('vendor_id', self.npduVendorID)
        # return what we built/updated
        return use_dict
