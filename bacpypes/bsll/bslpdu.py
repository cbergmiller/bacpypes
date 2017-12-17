from ..link import LocalStation
from ..comm import PDUData
from .bslci import BSLCI
from .registry import register_bslpdu_type

__all__ = [
    'BSLPDU', 'DeviceToDeviceAPDU', 'RouterToRouterNPDU', 'ProxyToServerBroadcastNPDU', 'ProxyToServerUnicastNPDU',
    'ServerToClientBroadcastAPDU', 'ServerToClientUnicastAPDU', 'ServerToProxyUnicastNPDU',
    'ServerToProxyBroadcastNPDU', 'ClientToLESBroadcastNPDU', 'ClientToLESUnicastNPDU', 'ClientToServerBroadcastAPDU',
    'ClientToServerUnicastAPDU', 'LESToClientBroadcastNPDU', 'LESToClientUnicastNPDU'
]


class BSLPDU(BSLCI, PDUData):
    """
    BSLPDU
    """

    def __init__(self, *args, **kwargs):
        super(BSLPDU, self).__init__(*args, **kwargs)

    def encode(self, pdu):
        BSLCI.encode(self, pdu)
        pdu.put_data(self.pduData)

    def decode(self, pdu):
        BSLCI.decode(self, pdu)
        self.pduData = pdu.get_data(len(pdu.pduData))


@register_bslpdu_type
class DeviceToDeviceAPDU(BSLPDU):
    """
    DeviceToDeviceAPDU
    """
    messageType = BSLCI.deviceToDeviceAPDU

    def __init__(self, *args, **kwargs):
        super(DeviceToDeviceAPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.deviceToDeviceAPDU
        self.bslciLength = 4 + len(self.pduData)

    def encode(self, bslpdu):
        # make sure the length is correct
        self.bslciLength = 4 + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


@register_bslpdu_type
class RouterToRouterNPDU(BSLPDU):
    """
    RouterToRouterNPDU
    """
    messageType = BSLCI.routerToRouterNPDU

    def __init__(self, *args, **kwargs):
        super(RouterToRouterNPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.routerToRouterNPDU
        self.bslciLength = 4 + len(self.pduData)

    def encode(self, bslpdu):
        # make sure the length is correct
        self.bslciLength = 4 + len(self.pduData)
        BSLCI.update(bslpdu, self)

        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


@register_bslpdu_type
class ProxyToServerUnicastNPDU(BSLPDU):
    """
    ProxyToServerUnicastNPDU
    """
    messageType = BSLCI.proxyToServerUnicastNPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ProxyToServerUnicastNPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.proxyToServerUnicastNPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


class ProxyToServerBroadcastNPDU(BSLPDU):
    """
    ProxyToServerBroadcastNPDU
    """
    messageType = BSLCI.proxyToServerBroadcastNPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ProxyToServerBroadcastNPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.proxyToServerBroadcastNPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


class ServerToProxyUnicastNPDU(BSLPDU):
    """
    ServerToProxyUnicastNPDU
    """
    messageType = BSLCI.serverToProxyUnicastNPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ServerToProxyUnicastNPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.serverToProxyUnicastNPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


class ServerToProxyBroadcastNPDU(BSLPDU):
    """
    ServerToProxyBroadcastNPDU
    """
    messageType = BSLCI.serverToProxyBroadcastNPDU

    def __init__(self, *args, **kwargs):
        super(ServerToProxyBroadcastNPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.serverToProxyBroadcastNPDU
        self.bslciLength = 4 + len(self.pduData)

    def encode(self, bslpdu):
        BSLCI.update(bslpdu, self)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


@register_bslpdu_type
class ClientToLESUnicastNPDU(BSLPDU):
    """
    ClientToLESUnicastNPDU
    """
    messageType = BSLCI.clientToLESUnicastNPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ClientToLESUnicastNPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.clientToLESUnicastNPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


class ClientToLESBroadcastNPDU(BSLPDU):
    """
    ClientToLESBroadcastNPDU
    """
    messageType = BSLCI.clientToLESBroadcastNPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ClientToLESBroadcastNPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.clientToLESBroadcastNPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


@register_bslpdu_type
class LESToClientUnicastNPDU(BSLPDU):
    """
    LESToClientUnicastNPDU
    """
    messageType = BSLCI.lesToClientUnicastNPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(LESToClientUnicastNPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.lesToClientUnicastNPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


class LESToClientBroadcastNPDU(BSLPDU):
    """
    LESToClientBroadcastNPDU
    """
    messageType = BSLCI.lesToClientBroadcastNPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(LESToClientBroadcastNPDU, self).__init__(*args, **kwargs)

        self.bslciFunction = BSLCI.lesToClientBroadcastNPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


class ClientToServerUnicastAPDU(BSLPDU):
    """
    ClientToServerUnicastAPDU
    """
    messageType = BSLCI.clientToServerUnicastAPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ClientToServerUnicastAPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.clientToServerUnicastAPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


@register_bslpdu_type
class ClientToServerBroadcastAPDU(BSLPDU):
    """
    ClientToServerBroadcastAPDU
    """
    messageType = BSLCI.clientToServerBroadcastAPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ClientToServerBroadcastAPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.clientToServerBroadcastAPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


class ServerToClientUnicastAPDU(BSLPDU):
    """
    ServerToClientUnicastAPDU
    """
    messageType = BSLCI.serverToClientUnicastAPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ServerToClientUnicastAPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.serverToClientUnicastAPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))


class ServerToClientBroadcastAPDU(BSLPDU):
    """
    ServerToClientBroadcastAPDU
    """
    messageType = BSLCI.serverToClientBroadcastAPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ServerToClientBroadcastAPDU, self).__init__(*args, **kwargs)
        self.bslciFunction = BSLCI.serverToClientBroadcastAPDU
        self.bslciLength = 5 + len(self.pduData)
        self.bslciAddress = addr
        if addr is not None:
            self.bslciLength += addr.addrLen

    def encode(self, bslpdu):
        addr_len = self.bslciAddress.addrLen
        # make sure the length is correct
        self.bslciLength = 5 + addr_len + len(self.pduData)
        BSLCI.update(bslpdu, self)
        # encode the address
        bslpdu.put(addr_len)
        bslpdu.put_data(self.bslciAddress.addrAddr)
        # encode the rest of the data
        bslpdu.put_data(self.pduData)

    def decode(self, bslpdu):
        BSLCI.update(self, bslpdu)
        # get the address
        addr_len = bslpdu.get()
        self.bslciAddress = LocalStation(bslpdu.get_data(addr_len))
        # get the rest of the data
        self.pduData = bslpdu.get_data(len(bslpdu.pduData))
