
import logging
from ..link import PCI
from .registry import *

_logger = logging.getLogger(__name__)
__all__ = ['APCI']


class APCI(PCI):
    """
    Application Layer Protcol Control Information
    """
    _debug_contents = (
        'apduType', 'apduSeg', 'apduMor', 'apduSA', 'apduSrv', 'apduNak', 'apduSeq', 'apduWin', 'apduMaxSegs',
        'apduMaxResp', 'apduService', 'apduInvokeID', 'apduAbortRejectReason'
    )

    def __init__(self, *args, **kwargs):
        super(APCI, self).__init__(*args, **kwargs)
        self.apduType = None
        self.apduSeg = None  # segmented
        self.apduMor = None  # more follows
        self.apduSA = None  # segmented response accepted
        self.apduSrv = None  # sent by server
        self.apduNak = None  # negative acknowledgement
        self.apduSeq = None  # sequence number
        self.apduWin = None  # actual/proposed window size
        self.apduMaxSegs = None  # maximum segments accepted (decoded)
        self.apduMaxResp = None  # max response accepted (decoded)
        self.apduService = None  #
        self.apduInvokeID = None  #
        self.apduAbortRejectReason = None  #

    def update(self, apci):
        PCI.update(self, apci)
        self.apduType = apci.apduType
        self.apduSeg = apci.apduSeg
        self.apduMor = apci.apduMor
        self.apduSA = apci.apduSA
        self.apduSrv = apci.apduSrv
        self.apduNak = apci.apduNak
        self.apduSeq = apci.apduSeq
        self.apduWin = apci.apduWin
        self.apduMaxSegs = apci.apduMaxSegs
        self.apduMaxResp = apci.apduMaxResp
        self.apduService = apci.apduService
        self.apduInvokeID = apci.apduInvokeID
        self.apduAbortRejectReason = apci.apduAbortRejectReason

    def __repr__(self):
        """Return a string representation of the PDU."""
        sname = f'{self.__module__}.{self.__class__.__name__}'
        # expand the type if possible
        atype = apdu_types.get(self.apduType, None)
        stype = atype.__name__ if atype else '?'
        # add the invoke ID if it has one
        if self.apduInvokeID is not None:
            stype += ',' + str(self.apduInvokeID)
        return f'<{sname}({stype}) instance at {hex(id(self))}>'

    def encode(self, pdu):
        """
        Encode the contents of the APCI into the PDU.
        (Concrete encode methods have been moved to the APDU classes)
        """
        PCI.update(pdu, self)
        apdu_cls = apdu_types.get(self.apduType)
        apdu_cls.encode_pdu(self, pdu)

    def decode(self, pdu):
        """
        Decode the contents of the PDU into the APCI.
        (Concrete decode methods have been moved to the APDU classes)
        """
        PCI.update(self, pdu)
        # decode the first octet
        buff = pdu.get()
        # decode and restore the APCI type
        self.apduType = (buff >> 4) & 0x0F
        apdu_cls = apdu_types.get(self.apduType)
        apdu_cls.decode_pdu(self, pdu, buff)

    def apci_contents(self, use_dict=None, as_class=dict):
        """
        Return the contents of an object as a dict.
        """
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # copy the source and destination to make it easier to search
        if self.pduSource:
            use_dict.__setitem__('source', str(self.pduSource))
        if self.pduDestination:
            use_dict.__setitem__('destination', str(self.pduDestination))
        apdu_cls = apdu_types.get(self.apduType)
        # loop through the elements
        for attr in APCI._debug_contents:
            value = getattr(self, attr, None)
            if value is None:
                continue
            if attr == 'apduType':
                mapped_value = apdu_types[self.apduType].__name__
            elif attr == 'apduService':
                mapped_value = apdu_cls.get_service_name(self.apduService)
            else:
                mapped_value = value
            # save the mapped value
            use_dict.__setitem__(attr, mapped_value)
        # return what we built/updated
        _logger.info('apci_contents %r', use_dict)
        return use_dict
