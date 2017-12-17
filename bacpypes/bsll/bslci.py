from ..debugging import DebugContents
from ..errors import EncodingError, DecodingError
from ..link import PCI
from .registry import register_bslpdu_type

__all__ = ['BSLCI', 'Result', 'ServiceRequest', 'AccessChallenge', 'AccessRequest', 'AccessResponse']


class BSLCI(PCI, DebugContents):
    """
    BSLCI
    """
    _debug_contents = ('bslciType', 'bslciFunction', 'bslciLength')

    result = 0x00
    serviceRequest = 0x01
    accessRequest = 0x02
    accessChallenge = 0x03
    accessResponse = 0x04
    deviceToDeviceAPDU = 0x05
    routerToRouterNPDU = 0x06
    proxyToServerUnicastNPDU = 0x07
    proxyToServerBroadcastNPDU = 0x08
    serverToProxyUnicastNPDU = 0x09
    serverToProxyBroadcastNPDU = 0x0A
    clientToLESUnicastNPDU = 0x0B
    clientToLESBroadcastNPDU = 0x0C
    lesToClientUnicastNPDU = 0x0D
    lesToClientBroadcastNPDU = 0x0E
    clientToServerUnicastAPDU = 0x0F
    clientToServerBroadcastAPDU = 0x10
    serverToClientUnicastAPDU = 0x11
    serverToClientBroadcastAPDU = 0x12

    def __init__(self, *args, **kwargs):
        super(BSLCI, self).__init__(*args, **kwargs)
        self.bslciType = 0x83
        self.bslciFunction = None
        self.bslciLength = None

    def update(self, bslci):
        PCI.update(self, bslci)
        self.bslciType = bslci.bslciType
        self.bslciFunction = bslci.bslciFunction
        self.bslciLength = bslci.bslciLength

    def encode(self, pdu):
        """encode the contents of the BSLCI into the PDU."""
        # copy the basics
        PCI.update(pdu, self)
        pdu.put(self.bslciType)  # 0x83
        pdu.put(self.bslciFunction)
        if self.bslciLength != len(self.pduData) + 4:
            raise EncodingError('invalid BSLCI length')
        pdu.put_short(self.bslciLength)

    def decode(self, pdu):
        """decode the contents of the PDU into the BSLCI."""
        # copy the basics
        PCI.update(self, pdu)
        self.bslciType = pdu.get()
        if self.bslciType != 0x83:
            raise DecodingError('invalid BSLCI type')
        self.bslciFunction = pdu.get()
        self.bslciLength = pdu.get_short()
        if self.bslciLength != len(pdu.pduData) + 4:
            raise DecodingError('invalid BSLCI length')


@register_bslpdu_type
class Result(BSLCI):
    """
    Result
    """

    messageType = BSLCI.result

    def __init__(self, code=None, *args, **kwargs):
        super(Result, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.result
        self.bslciLength = 6
        self.bslciResultCode = code

    def encode(self, bslpdu):
        BSLCI.update(bslpdu, self)
        bslpdu.put_short(self.bslciResultCode)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        self.bslciResultCode = bslpdu.get_short()


@register_bslpdu_type
class ServiceRequest(BSLCI):
    """
    ServiceRequest
    """
    messageType = BSLCI.serviceRequest

    def __init__(self, code=None, *args, **kwargs):
        super(ServiceRequest, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.serviceRequest
        self.bslciLength = 6
        self.bslciServiceID = code

    def encode(self, bslpdu):
        BSLCI.update(bslpdu, self)
        bslpdu.put_short(self.bslciServiceID)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        self.bslciServiceID = bslpdu.get_short()


@register_bslpdu_type
class AccessRequest(BSLCI):
    """
    AccessRequest
    """

    messageType = BSLCI.accessRequest

    def __init__(self, hashFn=0, username='', *args, **kwargs):
        super(AccessRequest, self).__init__(*args, **kwargs)

        self.bslciFunction = BSLCI.accessRequest
        self.bslciLength = 5
        self.bslciHashFn = hashFn
        self.bslciUsername = username
        if username:
            self.bslciLength += len(username)

    def encode(self, bslpdu):
        BSLCI.update(bslpdu, self)
        bslpdu.put(self.bslciHashFn)
        bslpdu.put_data(self.bslciUsername)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        self.bslciHashFn = bslpdu.get()
        self.bslciUsername = bslpdu.get_data(len(bslpdu.pduData))


@register_bslpdu_type
class AccessChallenge(BSLCI):
    """
    AccessChallenge
    """

    messageType = BSLCI.accessChallenge

    def __init__(self, hashFn=0, challenge='', *args, **kwargs):
        super(AccessChallenge, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.accessChallenge
        self.bslciLength = 5
        self.bslciHashFn = hashFn
        self.bslciChallenge = challenge
        if challenge:
            self.bslciLength += len(challenge)

    def encode(self, bslpdu):
        BSLCI.update(bslpdu, self)
        bslpdu.put(self.bslciHashFn)
        bslpdu.put_data(self.bslciChallenge)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        self.bslciHashFn = bslpdu.get()
        self.bslciChallenge = bslpdu.get_data(len(bslpdu.pduData))


@register_bslpdu_type
class AccessResponse(BSLCI):
    """
    AccessResponse
    """
    messageType = BSLCI.accessResponse

    def __init__(self, hashFn=0, response='', *args, **kwargs):
        super(AccessResponse, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.accessResponse
        self.bslciLength = 5
        self.bslciHashFn = hashFn
        self.bslciResponse = response
        if response:
            self.bslciLength += len(response)

    def encode(self, bslpdu):
        BSLCI.update(bslpdu, self)
        bslpdu.put(self.bslciHashFn)
        bslpdu.put_data(self.bslciResponse)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        self.bslciHashFn = bslpdu.get()
        self.bslciResponse = bslpdu.get_data(len(bslpdu.pduData))
