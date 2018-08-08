#!/usr/bin/python

"""
Analysis - Decoding pcap files

Before analyzing files, install libpcap-dev:
     $ sudo apt install libpcap-dev
 then install pypcap:
     https://github.com/pynetwork/pypcap
"""

import sys
import time
import socket
import struct
import logging

pcap = None
try:
    import pcap
except:
    pass

from .debugging import ModuleLogger, DebugContents, btox

from .link import PDU, Address
from .bvll import BVLPDU, bvl_pdu_types, ForwardedNPDU, \
    DistributeBroadcastToNetwork, OriginalUnicastNPDU, OriginalBroadcastNPDU
from .network import NPDU, npdu_types
from .apdu import APDU, apdu_types, confirmed_request_types, unconfirmed_request_types, complex_ack_types, error_types, \
    ConfirmedRequestPDU, UnconfirmedRequestPDU, SimpleAckPDU, ComplexAckPDU, SegmentAckPDU, ErrorPDU, RejectPDU, AbortPDU

# some debugging
DEBUG = False
_logger = logging.getLogger(__name__)

# protocol map
_protocols={socket.IPPROTO_TCP:'tcp',
           socket.IPPROTO_UDP:'udp',
           socket.IPPROTO_ICMP:'icmp'}


def strftimestamp(ts):
    return time.strftime("%d-%b-%Y %H:%M:%S", time.localtime(ts)) \
            + (".%06d" % ((ts - int(ts)) * 1000000,))


def decode_ethernet(s):
    if DEBUG: _logger.debug("decode_ethernet %s...", btox(s[:14], '.'))

    d={}
    d['destination_address'] = btox(s[0:6], ':')
    d['source_address'] = btox(s[6:12], ':')
    d['type'] = struct.unpack('!H',s[12:14])[0]
    d['data'] = s[14:]

    return d


def decode_vlan(s):
    if DEBUG: _logger.debug("decode_vlan %s...", btox(s[:4]))

    d = {}
    x = struct.unpack('!H',s[0:2])[0]
    d['priority'] = (x >> 13) & 0x07
    d['cfi'] = (x >> 12) & 0x01
    d['vlan'] = x & 0x0FFF
    d['type'] = struct.unpack('!H',s[2:4])[0]
    d['data'] = s[4:]

    return d


def decode_ip(s):
    if DEBUG: _logger.debug("decode_ip %r", btox(s[:20], '.'))

    d = {}
    d['version'] = (s[0] & 0xf0) >> 4
    d['header_len'] = s[0] & 0x0f
    d['tos'] = s[1]
    d['total_len'] = struct.unpack('!H', s[2:4])[0]
    d['id'] = struct.unpack('!H', s[4:6])[0]
    d['flags'] = (s[6] & 0xe0) >> 5
    d['fragment_offset'] = struct.unpack('!H', s[6:8])[0] & 0x1f
    d['ttl'] = s[8]
    d['protocol'] = _protocols.get(s[9], '0x%.2x ?' % s[9])
    d['checksum'] = struct.unpack('!H', s[10:12])[0]
    d['source_address'] = socket.inet_ntoa(s[12:16])
    d['destination_address'] = socket.inet_ntoa(s[16:20])
    if d['header_len'] > 5:
        d['options'] = s[20:4 * (d['header_len'] - 5)]
    else:
        d['options'] = None
    d['data'] = s[4 * d['header_len']:]

    return d


def decode_udp(s):
    if DEBUG: _logger.debug("decode_udp %s...", btox(s[:8]))

    d = {}
    d['source_port'] = struct.unpack('!H',s[0:2])[0]
    d['destination_port'] = struct.unpack('!H',s[2:4])[0]
    d['length'] = struct.unpack('!H',s[4:6])[0]
    d['checksum'] = struct.unpack('!H',s[6:8])[0]
    d['data'] = s[8:8 + d['length'] - 8]

    return d


def decode_packet(data):
    """decode the data, return some kind of PDU."""
    if DEBUG: _logger.debug("decode_packet %r", data)

    # empty strings are some other kind of pcap content
    if not data:
        return None

    # assume it is ethernet for now
    d = decode_ethernet(data)
    data = d['data']
    # there could be a VLAN header
    if (d['type'] == 0x8100):
        if DEBUG: _logger.debug("    - vlan found")
        d = decode_vlan(data)
        data = d['data']
    # look for IP packets
    if (d['type'] == 0x0800):
        if DEBUG: _logger.debug("    - IP found")
        d = decode_ip(data)
        pduSource, pduDestination = d['source_address'], d['destination_address']
        data = d['data']
        if (d['protocol'] == 'udp'):
            if DEBUG: _logger.debug("    - UDP found")
            d = decode_udp(data)
            data = d['data']
            pduSource = Address((pduSource, d['source_port']))
            pduDestination = Address((pduDestination, d['destination_port']))
            if DEBUG:
                _logger.debug("    - pduSource: %r", pduSource)
                _logger.debug("    - pduDestination: %r", pduDestination)
        else:
            if DEBUG: _logger.debug("    - not a UDP packet")
            return None
    else:
        if DEBUG: _logger.debug("    - not an IP packet")
        return None
    # check for empty
    if not data:
        if DEBUG: _logger.debug("    - empty packet")
        return None
    # build a PDU
    pdu = PDU(data, source=pduSource, destination=pduDestination)
    # check for a BVLL header
    if pdu.pduData[0] == '\x81':
        if DEBUG: _logger.debug("    - BVLL header found")
        xpdu = BVLPDU()
        xpdu.decode(pdu)
        pdu = xpdu
        # make a more focused interpretation
        atype = bvl_pdu_types.get(pdu.bvlciFunction)
        if not atype:
            if DEBUG: _logger.debug("    - unknown BVLL type: %r", pdu.bvlciFunction)
            return pdu
        # decode it as one of the basic types
        try:
            xpdu = pdu
            bpdu = atype()
            bpdu.decode(pdu)
            if DEBUG: _logger.debug("    - bpdu: %r", bpdu)
            pdu = bpdu
            # lift the address for forwarded NPDU's
            if atype is ForwardedNPDU:
                pdu.pduSource = bpdu.bvlciAddress
            # no deeper decoding for some
            elif atype not in (DistributeBroadcastToNetwork, OriginalUnicastNPDU, OriginalBroadcastNPDU):
                return pdu
        except Exception as err:
            if DEBUG: _logger.debug("    - decoding Error: %r", err)
            return xpdu
    # check for version number
    if pdu.pduData[0] != '\x01':
        if DEBUG: _logger.debug("    - not a version 1 packet: %s...", btox(pdu.pduData[:30], '.'))
        return None
    # it's an NPDU
    try:
        npdu = NPDU()
        npdu.decode(pdu)
    except Exception as err:
        if DEBUG: _logger.debug("    - decoding Error: %r", err)
        return None
    # application or network layer message
    if npdu.npduNetMessage is None:
        if DEBUG: _logger.debug("    - not a network layer message, try as an APDU")
        # decode as a generic APDU
        try:
            xpdu = APDU()
            xpdu.decode(npdu)
            apdu = xpdu
        except Exception as err:
            if DEBUG: _logger.debug("    - decoding Error: %r", err)
            return npdu
        # "lift" the source and destination address
        if npdu.npduSADR:
            apdu.pduSource = npdu.npduSADR
        else:
            apdu.pduSource = npdu.pduSource
        if npdu.npduDADR:
            apdu.pduDestination = npdu.npduDADR
        else:
            apdu.pduDestination = npdu.pduDestination
        # make a more focused interpretation
        atype = apdu_types.get(apdu.apduType)
        if not atype:
            if DEBUG: _logger.debug("    - unknown APDU type: %r", apdu.apduType)
            return apdu
        # decode it as one of the basic types
        try:
            xpdu = apdu
            apdu = atype()
            apdu.decode(xpdu)
        except Exception as err:
            if DEBUG: _logger.debug("    - decoding Error: %r", err)
            return xpdu

        # decode it at the next level
        if isinstance(apdu, ConfirmedRequestPDU):
            atype = confirmed_request_types.get(apdu.apduService)
            if not atype:
                if DEBUG: _logger.debug("    - no confirmed request decoder: %r", apdu.apduService)
                return apdu

        elif isinstance(apdu, UnconfirmedRequestPDU):
            atype = unconfirmed_request_types.get(apdu.apduService)
            if not atype:
                if DEBUG: _logger.debug("    - no unconfirmed request decoder: %r", apdu.apduService)
                return apdu

        elif isinstance(apdu, SimpleAckPDU):
            atype = None

        elif isinstance(apdu, ComplexAckPDU):
            atype = complex_ack_types.get(apdu.apduService)
            if not atype:
                if DEBUG: _logger.debug("    - no complex ack decoder: %r", apdu.apduService)
                return apdu

        elif isinstance(apdu, SegmentAckPDU):
            atype = None

        elif isinstance(apdu, ErrorPDU):
            atype = error_types.get(apdu.apduService)
            if not atype:
                if DEBUG: _logger.debug("    - no error decoder: %r", apdu.apduService)
                return apdu

        elif isinstance(apdu, RejectPDU):
            atype = None

        elif isinstance(apdu, AbortPDU):
            atype = None
        if DEBUG: _logger.debug("    - atype: %r", atype)

        # deeper decoding
        try:
            if atype:
                xpdu = apdu
                apdu = atype()
                apdu.decode(xpdu)
        except Exception as err:
            if DEBUG: _logger.debug("    - decoding error: %r", err)
            return xpdu

        # success
        return apdu

    else:
        # make a more focused interpretation
        ntype = npdu_types.get(npdu.npduNetMessage)
        if not ntype:
            if DEBUG: _logger.debug("    - no network layer decoder: %r", npdu.npduNetMessage)
            return npdu
        if DEBUG: _logger.debug("    - ntype: %r", ntype)

        # deeper decoding
        try:
            xpdu = npdu
            npdu = ntype()
            npdu.decode(xpdu)
        except Exception as err:
            if DEBUG: _logger.debug("    - decoding error: %r", err)
            return xpdu

        # success
        return npdu


def decode_file(fname):
    """Given the name of a pcap file, open it, decode the contents and yield each packet."""
    if DEBUG: _logger.debug("decode_file %r", fname)

    if not pcap:
        raise RuntimeError("failed to import pcap")

    # create a pcap object
    p = pcap.pcap(fname)

    for i, (timestamp, data) in enumerate(p):
        pkt = decode_packet(data)
        if not pkt:
            continue

        # save the packet number (as viewed in Wireshark) and timestamp
        pkt._number = i + 1
        pkt._timestamp = timestamp

        yield pkt


class Tracer(DebugContents):

    def __init__(self, initial_state=None):
        if DEBUG: _logger.debug("__init__ initial_state=%r", initial_state)

        # set the current state to the initial state
        self.next(initial_state or self.start)

    def next(self, fn):
        if DEBUG: _logger.debug("next %r", fn)

        # set the state
        self.current_state = fn

    def start(self, pkt):
        if DEBUG: _logger.debug("start %r", pkt)


def trace(fname, tracers):
    if DEBUG: _logger.debug("trace %r %r", fname, tracers)
    # make a list of tracers
    current_tracers = [traceClass() for traceClass in tracers]
    # decode the file
    for pkt in decode_file(fname):
        for i, tracer in enumerate(current_tracers):
            # give the packet to the tracer
            tracer.current_state(pkt)
            # if there is no current state, make a new one
            if not tracer.current_state:
                current_tracers[i] = tracers[i]()


if __name__ == "__main__":
    try:
        from bacpypes.consolelogging import ConsoleLogHandler

        if ('--debug' in sys.argv):
            indx = sys.argv.index('--debug')
            for i in range(indx+1, len(sys.argv)):
                ConsoleLogHandler(sys.argv[i])
            del sys.argv[indx:]

        _logger.debug("initialization")

        for pkt in decode_file(sys.argv[1]):
            print(strftimestamp(pkt._timestamp), pkt.__class__.__name__)
            pkt.debug_contents()
            print('')

    except KeyboardInterrupt:
        pass
    except Exception as err:
        _logger.exception("an error has occurred: %s", err)
    finally:
        _logger.debug("finally")
