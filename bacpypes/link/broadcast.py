
from .address import Address

__all__ = ['LocalBroadcast', 'RemoteBroadcast', 'GlobalBroadcast']


class LocalBroadcast(Address):
    """
    LocalBroadcast
    """
    def __init__(self):
        self.addrType = Address.localBroadcastAddr
        self.addrNet = None
        self.addrAddr = None
        self.addrLen = None


class RemoteBroadcast(Address):
    """
    RemoteBroadcast
    """
    def __init__(self, net):
        if not isinstance(net, int):
            raise TypeError('integer network required')
        if (net < 0) or (net >= 65535):
            raise ValueError('network out of range')
        self.addrType = Address.remoteBroadcastAddr
        self.addrNet = net
        self.addrAddr = None
        self.addrLen = None


class GlobalBroadcast(Address):
    """
    GlobalBroadcast
    """
    def __init__(self):
        self.addrType = Address.globalBroadcastAddr
        self.addrNet = None
        self.addrAddr = None
        self.addrLen = None
