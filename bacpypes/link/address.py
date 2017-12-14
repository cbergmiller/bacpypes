
import re
import socket
import struct
import logging

try:
    import netifaces
except ImportError:
    netifaces = None

from ..debugging import btox, xtob

# pack/unpack constants
_short_mask = 0xFFFF
_long_mask = 0xFFFFFFFF

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['Address', 'pack_ip_addr', 'unpack_ip_addr']

#
#   Address
#

ip_address_mask_port_re = re.compile(r'^(?:(\d+):)?(\d+\.\d+\.\d+\.\d+)(?:/(\d+))?(?::(\d+))?$')
ethernet_re = re.compile(r'^([0-9A-Fa-f][0-9A-Fa-f][:]){5}([0-9A-Fa-f][0-9A-Fa-f])$')
interface_re = re.compile(r'^(?:([\w]+))(?::(\d+))?$')


def pack_ip_addr(addr):
    """
    Given an IP address tuple like ('1.2.3.4', 47808) return the six-octet string useful for a BACnet address.
    """
    addr, port = addr
    return socket.inet_aton(addr) + struct.pack('!H', port & _short_mask)


def unpack_ip_addr(addr):
    """Given a six-octet BACnet address, return an IP address tuple."""
    if isinstance(addr, bytearray):
        addr = bytes(addr)
    return socket.inet_ntoa(addr[0:4]), struct.unpack('!H', addr[4:6])[0]


class Address:
    """
    Address
    """
    nullAddr = 0
    localBroadcastAddr = 1
    localStationAddr = 2
    remoteBroadcastAddr = 3
    remoteStationAddr = 4
    globalBroadcastAddr = 5

    def __init__(self, *args):
        if DEBUG: _logger.debug(f'__init__ {args!r}')
        self.addrType = Address.nullAddr
        self.addrNet = None
        self.addrLen = 0
        self.addrAddr = b''
        if len(args) == 1:
            self.decode_address(args[0])
        elif len(args) == 2:
            self.decode_address(args[1])
            if self.addrType == Address.localStationAddr:
                self.addrType = Address.remoteStationAddr
                self.addrNet = args[0]
            elif self.addrType == Address.localBroadcastAddr:
                self.addrType = Address.remoteBroadcastAddr
                self.addrNet = args[0]
            else:
                raise ValueError('unrecognized address ctor form')

    def decode_address(self, addr):
        """Initialize the address from a string.  Lots of different forms are supported."""
        if DEBUG: _logger.debug(f'decode_address {addr!r} ({type(addr)})')
        # start out assuming this is a local station
        self.addrType = Address.localStationAddr
        self.addrNet = None
        if addr == '*':
            if DEBUG: _logger.debug('    - localBroadcast')
            self.addrType = Address.localBroadcastAddr
            self.addrNet = None
            self.addrAddr = None
            self.addrLen = None

        elif addr == '*:*':
            if DEBUG: _logger.debug('   - globalBroadcast')
            self.addrType = Address.globalBroadcastAddr
            self.addrNet = None
            self.addrAddr = None
            self.addrLen = None

        elif isinstance(addr, int):
            if DEBUG: _logger.debug('    - int')
            if (addr < 0) or (addr >= 256):
                raise ValueError('address out of range')
            self.addrAddr = struct.pack('B', addr)
            self.addrLen = 1

        elif isinstance(addr, (bytes, bytearray)):
            if DEBUG: _logger.debug('    - bytes or bytearray')
            self.addrAddr = bytes(addr)
            self.addrLen = len(addr)

            if self.addrLen == 6:
                self.addrIP = struct.unpack('!L', addr[:4])[0]
                self.addrMask = (1 << 32) - 1
                self.addrHost = (self.addrIP & ~self.addrMask)
                self.addrSubnet = (self.addrIP & self.addrMask)
                self.addrPort = struct.unpack('>H', addr[4:])[0]
                self.addrTuple = (socket.inet_ntoa(addr[:4]), self.addrPort)
                self.addrBroadcastTuple = ('255.255.255.255', self.addrPort)

        elif isinstance(addr, str):
            if DEBUG: _logger.debug('    - str')
            m = ip_address_mask_port_re.match(addr)
            if m:
                if DEBUG: _logger.debug('    - IP address')
                net, addr, mask, port = m.groups()
                if not mask:
                    mask = '32'
                if not port:
                    port = '47808'
                if DEBUG: _logger.debug('    - net, addr, mask, port: %r, %r, %r, %r', net, addr, mask, port)
                if net:
                    net = int(net)
                    if net >= 65535:
                        raise ValueError('network out of range')
                    self.addrType = Address.remoteStationAddr
                    self.addrNet = net
                self.addrPort = int(port)
                self.addrTuple = (addr, self.addrPort)

                addrstr = socket.inet_aton(addr)
                self.addrIP = struct.unpack('!L', addrstr)[0]
                self.addrMask = (_long_mask << (32 - int(mask))) & _long_mask
                self.addrHost = (self.addrIP & ~self.addrMask)
                self.addrSubnet = (self.addrIP & self.addrMask)
                bcast = (self.addrSubnet | ~self.addrMask)
                self.addrBroadcastTuple = (socket.inet_ntoa(struct.pack('!L', bcast & _long_mask)), self.addrPort)
                self.addrAddr = addrstr + struct.pack('!H', self.addrPort & _short_mask)
                self.addrLen = 6

            elif ethernet_re.match(addr):
                if DEBUG: _logger.debug('    - ethernet')
                self.addrAddr = xtob(addr, ':')
                self.addrLen = len(self.addrAddr)

            elif re.match(r'^\d+$', addr):
                if DEBUG: _logger.debug('    - int')
                addr = int(addr)
                if addr > 255:
                    raise ValueError('address out of range')
                self.addrAddr = struct.pack('B', addr)
                self.addrLen = 1

            elif re.match(r'^\d+:[*]$', addr):
                if DEBUG: _logger.debug('    - remote broadcast')
                addr = int(addr[:-2])
                if addr >= 65535:
                    raise ValueError('network out of range')
                self.addrType = Address.remoteBroadcastAddr
                self.addrNet = addr
                self.addrAddr = None
                self.addrLen = None

            elif re.match(r'^\d+:\d+$', addr):
                if DEBUG: _logger.debug('    - remote station')
                net, addr = addr.split(':')
                net = int(net)
                addr = int(addr)
                if net >= 65535:
                    raise ValueError('network out of range')
                if addr > 255:
                    raise ValueError('address out of range')
                self.addrType = Address.remoteStationAddr
                self.addrNet = net
                self.addrAddr = struct.pack('B', addr)
                self.addrLen = 1

            elif re.match(r'^0x([0-9A-Fa-f][0-9A-Fa-f])+$', addr):
                if DEBUG: _logger.debug('    - modern hex string')
                self.addrAddr = xtob(addr[2:])
                self.addrLen = len(self.addrAddr)

            elif re.match(r"^X'([0-9A-Fa-f][0-9A-Fa-f])+'$", addr):
                if DEBUG: _logger.debug('    - old school hex string')

                self.addrAddr = xtob(addr[2:-1])
                self.addrLen = len(self.addrAddr)

            elif re.match(r'^\d+:0x([0-9A-Fa-f][0-9A-Fa-f])+$', addr):
                if DEBUG: _logger.debug('    - remote station with modern hex string')
                net, addr = addr.split(':')
                net = int(net)
                if net >= 65535:
                    raise ValueError('network out of range')
                self.addrType = Address.remoteStationAddr
                self.addrNet = net
                self.addrAddr = xtob(addr[2:])
                self.addrLen = len(self.addrAddr)

            elif re.match(r"^\d+:X'([0-9A-Fa-f][0-9A-Fa-f])+'$", addr):
                if DEBUG: _logger.debug('    - remote station with old school hex string')
                net, addr = addr.split(':')
                net = int(net)
                if net >= 65535:
                    raise ValueError('network out of range')

                self.addrType = Address.remoteStationAddr
                self.addrNet = net
                self.addrAddr = xtob(addr[2:-1])
                self.addrLen = len(self.addrAddr)

            elif netifaces and interface_re.match(addr):
                if DEBUG: _logger.debug('    - interface name with optional port')
                interface, port = interface_re.match(addr).groups()
                if port is not None:
                    self.addrPort = int(port)
                else:
                    self.addrPort = 47808
                interfaces = netifaces.interfaces()
                if interface not in interfaces:
                    raise ValueError('not an interface: %s' % (interface,))
                if DEBUG: _logger.debug('    - interfaces: %r', interfaces)
                ifaddresses = netifaces.ifaddresses(interface)
                if netifaces.AF_INET not in ifaddresses:
                    raise ValueError('interface does not support IPv4: %s' % (interface,))
                ipv4addresses = ifaddresses[netifaces.AF_INET]
                if len(ipv4addresses) > 1:
                    raise ValueError('interface supports multiple IPv4 addresses: %s' % (interface,))
                ifaddress = ipv4addresses[0]
                if DEBUG: _logger.debug('    - ifaddress: %r', ifaddress)
                addr = ifaddress['addr']
                self.addrTuple = (addr, self.addrPort)
                if DEBUG: _logger.debug('    - addrTuple: %r', self.addrTuple)
                addrstr = socket.inet_aton(addr)
                self.addrIP = struct.unpack('!L', addrstr)[0]
                if 'netmask' in ifaddress:
                    maskstr = socket.inet_aton(ifaddress['netmask'])
                    self.addrMask = struct.unpack('!L', maskstr)[0]
                else:
                    self.addrMask = _long_mask
                self.addrHost = (self.addrIP & ~self.addrMask)
                self.addrSubnet = (self.addrIP & self.addrMask)
                if 'broadcast' in ifaddress:
                    self.addrBroadcastTuple = (ifaddress['broadcast'], self.addrPort)
                else:
                    self.addrBroadcastTuple = None
                if DEBUG: _logger.debug('    - addrBroadcastTuple: %r', self.addrBroadcastTuple)
                self.addrAddr = addrstr + struct.pack('!H', self.addrPort & _short_mask)
                self.addrLen = 6
            else:
                raise ValueError('unrecognized format')

        elif isinstance(addr, tuple):
            addr, port = addr
            self.addrPort = int(port)
            if isinstance(addr, str):
                if not addr:
                    # when ('', n) is passed it is the local host address, but that
                    # could be more than one on a multihomed machine, the empty string
                    # means "any".
                    addrstr = b'\0\0\0\0'
                else:
                    addrstr = socket.inet_aton(addr)
                self.addrTuple = (addr, self.addrPort)
            elif isinstance(addr, int):
                addrstr = struct.pack('!L', addr & _long_mask)
                self.addrTuple = (socket.inet_ntoa(addrstr), self.addrPort)
            else:
                raise TypeError('tuple must be (string, port) or (long, port)')
            if DEBUG: _logger.debug('    - addrstr: %r', addrstr)
            self.addrIP = struct.unpack('!L', addrstr)[0]
            self.addrMask = _long_mask
            self.addrHost = None
            self.addrSubnet = None
            self.addrBroadcastTuple = self.addrTuple
            self.addrAddr = addrstr + struct.pack('!H', self.addrPort & _short_mask)
            self.addrLen = 6
        else:
            raise TypeError('integer, string or tuple required')

    def __str__(self):
        if self.addrType == Address.nullAddr:
            return 'Null'
        elif self.addrType == Address.localBroadcastAddr:
            return '*'
        elif self.addrType == Address.localStationAddr:
            rslt = ''
            if self.addrLen == 1:
                rslt += str(self.addrAddr[0])
            else:
                port = struct.unpack('!H', self.addrAddr[-2:])[0]
                if (len(self.addrAddr) == 6) and (port >= 47808) and (port <= 47823):
                    rslt += '.'.join(['%d' % (x) for x in self.addrAddr[0:4]])
                    if port != 47808:
                        rslt += ':' + str(port)
                else:
                    rslt += '0x' + btox(self.addrAddr)
            return rslt
        elif self.addrType == Address.remoteBroadcastAddr:
            return '%d:*' % (self.addrNet,)
        elif self.addrType == Address.remoteStationAddr:
            rslt = '%d:' % (self.addrNet,)
            if self.addrLen == 1:
                rslt += str(self.addrAddr[0])
            else:
                port = struct.unpack('!H', self.addrAddr[-2:])[0]
                if (len(self.addrAddr) == 6) and (port >= 47808) and (port <= 47823):
                    rslt += '.'.join(['%d' % (x) for x in self.addrAddr[0:4]])
                    if port != 47808:
                        rslt += ':' + str(port)
                else:
                    rslt += '0x' + btox(self.addrAddr)
            return rslt
        elif self.addrType == Address.globalBroadcastAddr:
            return '*:*'
        else:
            raise TypeError('unknown address type %d' % self.addrType)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.__str__())

    def __hash__(self):
        return hash((self.addrType, self.addrNet, self.addrAddr))

    def __eq__(self, arg):
        # try an coerce it into an address
        if not isinstance(arg, Address):
            arg = Address(arg)
        # all of the components must match
        return (self.addrType == arg.addrType) and (self.addrNet == arg.addrNet) and (self.addrAddr == arg.addrAddr)

    def __ne__(self, arg):
        return not self.__eq__(arg)

    def dict_contents(self, use_dict=None, as_class=None):
        """Return the contents of an object as a dict."""
        if DEBUG: _logger.debug(f'dict_contents use_dict={use_dict!r} as_class={as_class!r}', use_dict, as_class)
        # exception to the rule of returning a dict
        return str(self)
