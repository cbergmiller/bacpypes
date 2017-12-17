
import logging

from ..link import Address
from ..network import NPDU
from .constants import *
from .bslci import *
from .bslpdu import *
from .connection_state import ConnectionState
from .net_service_adapter import NetworkServiceAdapter

_logger = logging.getLogger(__name__)
__all__ = ['DeviceToDeviceServerService', 'DeviceToDeviceClientService']


class DeviceToDeviceServerService(NetworkServiceAdapter):
    """
    DeviceToDeviceServerService
    """
    serviceID = DEVICE_TO_DEVICE_SERVICE_ID

    def process_npdu(self, npdu):
        """encode NPDUs from the service access point and send them downstream."""
        # broadcast messages go to peers
        if npdu.pduDestination.addrType == Address.localBroadcastAddr:
            dest_list = self.connections.keys()
        else:
            if npdu.pduDestination not in self.connections:
                # not a connected client
                return
            dest_list = [npdu.pduDestination]
        for dest in dest_list:
            # make device-to-device APDU
            xpdu = DeviceToDeviceAPDU(npdu)
            xpdu.pduDestination = dest
            # send it down to the multiplexer
            self.service_request(xpdu)

    def service_confirmation(self, conn, pdu):
        # build an NPDU
        npdu = NPDU(pdu.pduData)
        npdu.pduSource = pdu.pduSource
        # send it to the service access point for processing
        self.adapterSAP.process_npdu(self, npdu)


class DeviceToDeviceClientService(NetworkServiceAdapter):
    serviceID = DEVICE_TO_DEVICE_SERVICE_ID

    def process_npdu(self, npdu):
        """encode NPDUs from the service access point and send them downstream."""
        # broadcast messages go to everyone
        if npdu.pduDestination.addrType == Address.localBroadcastAddr:
            dest_list = self.connections.keys()
        else:
            conn = self.connections.get(npdu.pduDestination, None)
            if not conn:
                # not a connected client
                # start a connection attempt
                conn = self.connect(npdu.pduDestination)
            if not conn.connected:
                # keep a reference to this npdu to send after the ack comes back
                conn.pendingNPDU.append(npdu)
                return
            dest_list = [npdu.pduDestination]
        for dest in dest_list:
            # make device-to-device APDU
            xpdu = DeviceToDeviceAPDU(npdu)
            xpdu.pduDestination = dest
            # send it down to the multiplexer
            self.service_request(xpdu)

    def connect(self, addr):
        """Initiate a connection request to the device."""
        # make a connection
        conn = ConnectionState(addr)
        self.multiplexer.connections[addr] = conn
        # associate with this service, but it is not connected until the ack comes back
        conn.service = self
        # keep a list of pending NPDU objects until the ack comes back
        conn.pendingNPDU = []
        # build a service request
        request = ServiceRequest(DEVICE_TO_DEVICE_SERVICE_ID)
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
                    # make device-to-device APDU
                    xpdu = DeviceToDeviceAPDU(npdu)
                    xpdu.pduDestination = npdu.pduDestination
                    # send it down to the multiplexer
                    self.service_request(xpdu)
                conn.pendingNPDU = []
        else:
            pass

    def service_confirmation(self, conn, pdu):
        # build an NPDU
        npdu = NPDU(pdu.pduData)
        npdu.pduSource = pdu.pduSource
        # send it to the service access point for processing
        self.adapterSAP.process_npdu(self, npdu)
