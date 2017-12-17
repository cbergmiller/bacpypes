import sys
import struct
import logging
from copy import copy as _copy

from ..errors import DecodingError
from ..debugging import btox

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['PDUData']

# prevent short/long struct overflow
_short_mask = 0xFFFF
_long_mask = 0xFFFFFFFF


class PDUData:
    """
    PDUData
    """

    def __init__(self, data=None, *args, **kwargs):
        if DEBUG: _logger.debug('__init__ %r %r %r', data, args, kwargs)
        # this call will fail if there are args or kwargs, but not if there
        # is another class in the __mro__ of this thing being constructed
        super(PDUData, self).__init__(*args, **kwargs)
        from .pdu import PDU
        # function acts like a copy constructor
        if data is None:
            self.pduData = bytearray()
        elif isinstance(data, (bytes, bytearray)):
            self.pduData = bytearray(data)
        elif isinstance(data, PDUData) or isinstance(data, PDU):
            self.pduData = _copy(data.pduData)
        else:
            raise TypeError('bytes or bytearray expected')

    def get(self):
        if len(self.pduData) == 0:
            raise DecodingError('no more packet data')
        octet = self.pduData[0]
        del self.pduData[0]
        return octet

    def get_data(self, dlen):
        if len(self.pduData) < dlen:
            raise DecodingError('no more packet data')
        data = self.pduData[:dlen]
        del self.pduData[:dlen]
        return data

    def get_short(self):
        return struct.unpack('>H', self.get_data(2))[0]

    def get_long(self):
        return struct.unpack('>L', self.get_data(4))[0]

    def put(self, n):
        # pduData is a bytearray
        self.pduData += bytes([n])

    def put_data(self, data):
        if isinstance(data, bytes):
            pass
        elif isinstance(data, bytearray):
            pass
        elif isinstance(data, list):
            data = bytes(data)
        else:
            raise TypeError('data must be bytes, bytearray, or a list')
        # regular append works
        self.pduData += data

    def put_short(self, n):
        self.pduData += struct.pack('>H', n & _short_mask)

    def put_long(self, n):
        self.pduData += struct.pack('>L', n & _long_mask)

    def debug_contents(self, indent=1, file=sys.stdout, _ids=None):
        tab = '    ' * indent
        if isinstance(self.pduData, bytearray):
            if len(self.pduData) > 20:
                hexed = btox(self.pduData[:20], '.') + '...'
            else:
                hexed = btox(self.pduData, '.')
            file.write("%spduData = x'%s'\n" % ('    ' * indent, hexed))
        else:
            file.write('%spduData = %r\n' % ('    ' * indent, self.pduData))

    def pdudata_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if DEBUG: _logger.debug('pdudata_contents use_dict=%r as_class=%r', use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # add the data if it is not None
        v = self.pduData
        if v is not None:
            if isinstance(v, bytearray):
                v = btox(v)
            elif hasattr(v, 'dict_contents'):
                v = v.dict_contents(as_class=as_class)
            use_dict.__setitem__('data', v)
        # return what we built/updated
        return use_dict

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if DEBUG: _logger.debug('dict_contents use_dict=%r as_class=%r', use_dict, as_class)
        return self.pdudata_contents(use_dict=use_dict, as_class=as_class)
