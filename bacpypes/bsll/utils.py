#!/usr/bin/python

"""
BACnet Streaming Link Layer Service
"""

import logging

from ..transport import StreamToPacket

_logger = logging.getLogger(__name__)


def _Packetize(data):
    """
    _Packetize
    """
    # look for the type field
    start_ind = data.find('\x83')
    if start_ind == -1:
        return None
    # chop off everything up to the start, it's garbage
    if start_ind > 0:
        data = data[start_ind:]
    # make sure we have at least a complete header
    if len(data) < 4:
        return None
    # get the length, make sure we have the whole packet
    total_len = (ord(data[2]) << 8) + ord(data[3])
    if len(data) < total_len:
        return None
    packet_slice = (data[:total_len], data[total_len:])
    return packet_slice


class _StreamToPacket(StreamToPacket):
    """
    _StreamToPacket
    """

    def __init__(self):
        StreamToPacket.__init__(self, _Packetize)

    def indication(self, pdu):
        self.request(pdu)


