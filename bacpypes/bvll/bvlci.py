import logging
from ..errors import EncodingError, DecodingError
from ..debugging import DebugContents
from ..link import PCI

# some debugging
_logger = logging.getLogger(__name__)
__all__ = ['BVLCI']


class BVLCI(PCI, DebugContents):
    """
    BACnet Virtual Link Layer Module
    """
    _debug_contents = ('bvlciType', 'bvlciFunction', 'bvlciLength')

    result = 0x00
    writeBroadcastDistributionTable = 0x01
    readBroadcastDistributionTable = 0x02
    readBroadcastDistributionTableAck = 0x03
    forwardedNPDU = 0x04
    registerForeignDevice = 0x05
    readForeignDeviceTable = 0x06
    readForeignDeviceTableAck = 0x07
    deleteForeignDeviceTableEntry = 0x08
    distributeBroadcastToNetwork = 0x09
    originalUnicastNPDU = 0x0A
    originalBroadcastNPDU = 0x0B

    def __init__(self, *args, **kwargs):
        _logger.debug("__init__ %r %r", args, kwargs)
        super(BVLCI, self).__init__(*args, **kwargs)

        self.bvlciType = 0x81
        self.bvlciFunction = None
        self.bvlciLength = None

    def update(self, bvlci):
        PCI.update(self, bvlci)
        self.bvlciType = bvlci.bvlciType
        self.bvlciFunction = bvlci.bvlciFunction
        self.bvlciLength = bvlci.bvlciLength

    def encode(self, pdu):
        """encode the contents of the BVLCI into the PDU."""
        _logger.debug("encode %s", str(pdu))

        # copy the basics
        PCI.update(pdu, self)

        pdu.put(self.bvlciType)  # 0x81
        pdu.put(self.bvlciFunction)

        if (self.bvlciLength != len(self.pduData) + 4):
            raise EncodingError("invalid BVLCI length")

        pdu.put_short(self.bvlciLength)

    def decode(self, pdu):
        """decode the contents of the PDU into the BVLCI."""
        _logger.debug("decode %s", str(pdu))

        # copy the basics
        PCI.update(self, pdu)

        self.bvlciType = pdu.get()
        if self.bvlciType != 0x81:
            raise DecodingError("invalid BVLCI type")

        self.bvlciFunction = pdu.get()
        self.bvlciLength = pdu.get_short()

        if (self.bvlciLength != len(pdu.pduData) + 4):
            raise DecodingError("invalid BVLCI length")

    def bvlci_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        _logger.debug("bvlci_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # save the mapped value
        use_dict.__setitem__('type', self.bvlciType)
        use_dict.__setitem__('function', self.bvlciFunction)
        use_dict.__setitem__('length', self.bvlciLength)

        # return what we built/updated
        return use_dict
