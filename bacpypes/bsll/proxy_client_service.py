
import logging

from ..comm import Client
from ..link import Address, LocalBroadcast, PDU
from .constants import *
from .bslci import *
from .bslpdu import *
from .connection_state import ConnectionState
from .service_adapter import ServiceAdapter

_logger = logging.getLogger(__name__)
__all__ = ['ProxyClientService']


class ProxyClientService(ServiceAdapter, Client):
    """
    ProxyClientService
    """
    serviceID = PROXY_SERVICE_ID

    def __init__(self, mux, addr=None, userinfo=None, cid=None):
        ServiceAdapter.__init__(self, mux)
        Client.__init__(self, cid)

        # save the address of the server and the userinfo
        self.address = addr
        self.userinfo = userinfo

    def get_default_user_info(self, addr):
        """get the user information to authenticate."""
        return self.userinfo

    def connect(self, addr=None, userinfo=None):
        """Initiate a connection request to the device."""
        # if the address was provided, use it
        if addr:
            self.address = addr
        else:
            addr = self.address
        # if the user was provided, save it
        if userinfo:
            self.userinfo = userinfo
        # make a connection
        conn = ConnectionState(addr)
        self.multiplexer.connections[addr] = conn
        # associate with this service, but it is not connected until the ack comes back
        conn.service = self
        # keep a list of pending BSLPDU objects until the ack comes back
        conn.pendingBSLPDU = []
        # build a service request
        request = ServiceRequest(PROXY_SERVICE_ID)
        request.pduDestination = addr
        # send it
        self.service_request(request)
        # return the connection object
        return conn

    def connect_ack(self, conn, bslpdu):
        # if the response is good, consider it connected
        if bslpdu.bslciResultCode == 0:
            # send the pending NPDU if there is one
            if conn.pendingBSLPDU:
                for pdu in conn.pendingBSLPDU:
                    # send it down to the multiplexer
                    self.service_request(pdu)
                conn.pendingBSLPDU = []
        else:
            _logger.warning('connection nack: %r', bslpdu.bslciResultCode)

    def service_confirmation(self, conn, bslpdu):
        # build a PDU
        pdu = PDU(bslpdu)
        if isinstance(bslpdu, ServerToProxyUnicastNPDU):
            pdu.pduDestination = bslpdu.bslciAddress
        elif isinstance(bslpdu, ServerToProxyBroadcastNPDU):
            pdu.pduDestination = LocalBroadcast()
        # send it downstream
        self.request(pdu)

    def confirmation(self, pdu):
        # we should at least have an address
        if not self.address:
            raise RuntimeError('no connection address')
        # build a bslpdu
        if pdu.pduDestination.addrType == Address.localBroadcastAddr:
            request = ProxyToServerBroadcastNPDU(pdu.pduSource, pdu)
        else:
            request = ProxyToServerUnicastNPDU(pdu.pduSource, pdu)
        request.pduDestination = self.address
        # make sure there is a connection
        conn = self.connections.get(self.address, None)
        if not conn:
            # not a connected client
            # start a connection attempt
            conn = self.connect()
        # if the connection is not connected, queue it, othersize send it
        if not conn.connected:
            # keep a reference to this npdu to send after the ack comes back
            conn.pendingBSLPDU.append(request)
        else:
            # send it
            self.service_request(request)
