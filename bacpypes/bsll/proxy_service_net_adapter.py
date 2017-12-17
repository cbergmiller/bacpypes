
import logging

from ..link import Address, LocalBroadcast, PDU
from ..network import NPDU, NetworkAdapter
from .bslpdu import *

_logger = logging.getLogger(__name__)
__all__ = ['ProxyServiceNetworkAdapter']


class ProxyServiceNetworkAdapter(NetworkAdapter):
    """
    ProxyServiceNetworkAdapter
    """

    def __init__(self, conn, sap, net, cid=None):
        NetworkAdapter.__init__(self, sap, net, cid)
        # save the connection
        self.conn = conn

    def process_npdu(self, npdu):
        """encode NPDUs from the network service access point and send them to the proxy."""
        # encode the npdu as if it was about to be delivered to the network
        pdu = PDU()
        npdu.encode(pdu)
        # broadcast messages go to peers
        if pdu.pduDestination.addrType == Address.localBroadcastAddr:
            xpdu = ServerToProxyBroadcastNPDU(pdu)
        else:
            xpdu = ServerToProxyUnicastNPDU(pdu.pduDestination, pdu)
        # the connection has the correct address
        xpdu.pduDestination = self.conn.address
        # send it down to the multiplexer
        self.conn.service.service_request(xpdu)

    def service_confirmation(self, bslpdu):
        """Receive packets forwarded by the proxy and send them upstream to the network service access point."""
        # build a PDU
        pdu = NPDU(bslpdu.pduData)
        # the source is from the original source, not the proxy itself
        pdu.pduSource = bslpdu.bslciAddress
        # if the proxy received a broadcast, send it upstream as a broadcast
        if isinstance(bslpdu, ProxyToServerBroadcastNPDU):
            pdu.pduDestination = LocalBroadcast()
        # decode it, the nework layer needs NPDUs
        npdu = NPDU()
        npdu.decode(pdu)
        # send it to the service access point for processing
        self.adapterSAP.process_npdu(self, npdu)
