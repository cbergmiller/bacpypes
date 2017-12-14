
import struct
from .address import Address

__all__ = ['LocalStation', 'RemoteStation']


class LocalStation(Address):
    """
    LocalStation
    """
    def __init__(self, addr):
        self.addrType = Address.localStationAddr
        self.addrNet = None
        if isinstance(addr, int):
            if (addr < 0) or (addr >= 256):
                raise ValueError('address out of range')
            self.addrAddr = struct.pack('B', addr)
            self.addrLen = 1
        elif isinstance(addr, (bytes, bytearray)):
            self.addrAddr = bytes(addr)
            self.addrLen = len(addr)
        else:
            raise TypeError('integer, bytes or bytearray required')


class RemoteStation(Address):
    """
    RemoteStation
    """
    def __init__(self, net, addr):
        if not isinstance(net, int):
            raise TypeError('integer network required')
        if (net < 0) or (net >= 65535):
            raise ValueError('network out of range')
        self.addrType = Address.remoteStationAddr
        self.addrNet = net
        if isinstance(addr, int):
            if (addr < 0) or (addr >= 256):
                raise ValueError('address out of range')
            self.addrAddr = struct.pack('B', addr)
            self.addrLen = 1
        elif isinstance(addr, (bytes, bytearray)):
            self.addrAddr = bytes(addr)
            self.addrLen = len(addr)
        else:
            raise TypeError('integer, bytes or bytearray required')