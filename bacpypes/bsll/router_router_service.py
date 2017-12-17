
import logging

from ..link import Address, PDU
from ..network import NPDU
from .constants import *
from .bslci import *
from .bslpdu import *
from .connection_state import ConnectionState
from .net_service_adapter import NetworkServiceAdapter

_logger = logging.getLogger(__name__)
__all__ = ['RouterToRouterService']


class RouterToRouterService(NetworkServiceAdapter):
    """
    RouterToRouterService
    """
    serviceID = ROUTER_TO_ROUTER_SERVICE_ID

    def process_npdu(self, npdu):
        """encode NPDUs from the service access point and send them downstream."""
        # encode the npdu as if it was about to be delivered to the network
        pdu = PDU()
        npdu.encode(pdu)
        # broadcast messages go to everyone
        if pdu.pduDestination.addrType == Address.localBroadcastAddr:
            dest_list = self.connections.keys()
        else:
            conn = self.connections.get(pdu.pduDestination, None)
            if not conn:
                # not a connected client
                # start a connection attempt
                conn = self.connect(pdu.pduDestination)
            if not conn.connected:
                # keep a reference to this pdu to send after the ack comes back
                conn.pendingNPDU.append(pdu)
                return
            dest_list = [pdu.pduDestination]
        for dest in dest_list:
            # make a router-to-router NPDU
            xpdu = RouterToRouterNPDU(pdu)
            xpdu.pduDestination = dest

            # send it to the multiplexer
            self.service_request(xpdu)

    def connect(self, addr):
        """Initiate a connection request to the peer router."""
        # make a connection
        conn = ConnectionState(addr)
        self.multiplexer.connections[addr] = conn
        # associate with this service, but it is not connected until the ack comes back
        conn.service = self
        # keep a list of pending NPDU objects until the ack comes back
        conn.pendingNPDU = []
        # build a service request
        request = ServiceRequest(ROUTER_TO_ROUTER_SERVICE_ID)
        request.pduDestination = addr
        # send it
        self.service_request(request)
        # return the connection object
        return conn

    def connect_ack(self, conn, pdu):
        # if the response is good, consider it connected
        if pdu.bslciResultCode == 0:
            # send the pending NPDU if there is one
            if conn.pendingNPDU:
                for npdu in conn.pendingNPDU:
                    # make router-to-router NPDU
                    xpdu = RouterToRouterNPDU(npdu)
                    xpdu.pduDestination = npdu.pduDestination
                    # send it down to the multiplexer
                    self.service_request(xpdu)
                conn.pendingNPDU = []
        else:
            pass

    def add_connection(self, conn):
        # first do the usual things
        NetworkServiceAdapter.add_connection(self, conn)
        # generate a Who-Is-Router-To-Network, all networks
        # send it to the client

    def remove_connection(self, conn):
        # first to the usual thing
        NetworkServiceAdapter.remove_connection(self, conn)
        # the NSAP needs routing table information related to this connection flushed
        self.adapterSAP.remove_router_references(self, conn.address)

    def service_confirmation(self, conn, pdu):
        # decode it, the nework layer needs NPDUs
        npdu = NPDU()
        npdu.decode(pdu)
        npdu.pduSource = pdu.pduSource
        # send it to the service access point for processing
        self.adapterSAP.process_npdu(self, npdu)
