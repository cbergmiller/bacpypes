#!/usr/bin/python

"""
TCP Communications Module
"""

from ..debugging import ModuleLogger, bacpypes_debugging
from ..comm import PDU, Client, Server
from ..comm import ServiceAccessPoint, ApplicationServiceElement

# some debugging
_debug = 0
_log = ModuleLogger(globals())
__all__ = ['StreamToPacket', 'StreamToPacketSAP']


@bacpypes_debugging
class StreamToPacket(Client, Server):

    def __init__(self, fn, cid=None, sid=None):
        if _debug: StreamToPacket._debug("__init__ %r cid=%r, sid=%r", fn, cid, sid)
        Client.__init__(self, cid)
        Server.__init__(self, sid)
        # save the packet function
        self.packetFn = fn
        # start with an empty set of buffers
        self.upstreamBuffer = {}
        self.downstreamBuffer = {}

    def packetize(self, pdu, streamBuffer):
        if _debug: StreamToPacket._debug("packetize %r ...", pdu)

        def chop(addr):
            if _debug: StreamToPacket._debug("chop %r", addr)
            # get the current downstream buffer
            buff = streamBuffer.get(addr, b'') + pdu.pduData
            if _debug: StreamToPacket._debug("    - buff: %r", buff)
            # look for a packet
            while 1:
                packet = self.packetFn(buff)
                if _debug: StreamToPacket._debug("    - packet: %r", packet)
                if packet is None:
                    break
                yield PDU(packet[0],
                    source=pdu.pduSource,
                    destination=pdu.pduDestination,
                    user_data=pdu.pduUserData,
                    )
                buff = packet[1]
            # save what didn't get sent
            streamBuffer[addr] = buff
        # buffer related to the addresses
        if pdu.pduSource:
            for pdu in chop(pdu.pduSource):
                yield pdu
        if pdu.pduDestination:
            for pdu in chop(pdu.pduDestination):
                yield pdu

    def indication(self, pdu):
        """Message going downstream."""
        if _debug: StreamToPacket._debug("indication %r", pdu)
        # hack it up into chunks
        for packet in self.packetize(pdu, self.downstreamBuffer):
            self.request(packet)

    def confirmation(self, pdu):
        """Message going upstream."""
        if _debug: StreamToPacket._debug("StreamToPacket.confirmation %r", pdu)
        # hack it up into chunks
        for packet in self.packetize(pdu, self.upstreamBuffer):
            self.response(packet)

#
#   StreamToPacketSAP
#

@bacpypes_debugging
class StreamToPacketSAP(ApplicationServiceElement, ServiceAccessPoint):

    def __init__(self, stp, aseID=None, sapID=None):
        if _debug: StreamToPacketSAP._debug("__init__ %r aseID=%r, sapID=%r", stp, aseID, sapID)
        ApplicationServiceElement.__init__(self, aseID)
        ServiceAccessPoint.__init__(self, sapID)
        # save a reference to the StreamToPacket object
        self.stp = stp

    def indication(self, add_actor=None, del_actor=None, actor_error=None, error=None):
        if _debug: StreamToPacketSAP._debug("indication add_actor=%r del_actor=%r", add_actor, del_actor)
        if add_actor:
            # create empty buffers associated with the peer
            self.stp.upstreamBuffer[add_actor.peer] = b''
            self.stp.downstreamBuffer[add_actor.peer] = b''
        if del_actor:
            # delete the buffer contents associated with the peer
            del self.stp.upstreamBuffer[del_actor.peer]
            del self.stp.downstreamBuffer[del_actor.peer]
        # chain this along
        if self.serviceElement:
            self.sap_request(
                add_actor=add_actor,
                del_actor=del_actor,
                actor_error=actor_error, error=error,
                )
