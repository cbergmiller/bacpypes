
import logging
from .constants import *
_logger = logging.getLogger(__name__)
__all__ = ['ServiceAdapter']


class ServiceAdapter:
    """
    ServiceAdapter
    """
    _authentication_required = False

    def __init__(self, mux):
        # keep a reference to the multiplexer
        self.multiplexer = mux
        # each multiplex adapter keeps a dict of its connections
        self.connections = {}
        # update the multiplexer to reference this adapter
        if self.serviceID == DEVICE_TO_DEVICE_SERVICE_ID:
            mux.deviceToDeviceService = self
        elif self.serviceID == ROUTER_TO_ROUTER_SERVICE_ID:
            mux.routerToRouterService = self
        elif self.serviceID == PROXY_SERVICE_ID:
            mux.proxyService = self
        elif self.serviceID == LANE_SERVICE_ID:
            mux.laneService = self
        else:
            raise RuntimeError(f'invalid service ID: {self.serviceID}')

    def authentication_required(self, addr):
        """
        Return True if authentication is required for connection requests from the address.
        """
        return self._authentication_required

    def get_default_user_info(self, addr):
        """Return a UserInformation object for trusted address->user authentication."""
        # no users
        return None

    def get_user_info(self, username):
        """Return a UserInformation object or None."""
        # no users
        return None

    def add_connection(self, conn):
        # keep track of this connection
        self.connections[conn.address] = conn
        # assume it is happily connected
        conn.service = self
        conn.connected = True

    def remove_connection(self, conn):
        try:
            del self.connections[conn.address]
        except KeyError:
            _logger.warning('remove_connection: %r not a connection', conn)
        # clear out the connection attributes
        conn.service = None
        conn.connected = False

    def service_request(self, pdu):
        # direct requests to the multiplexer
        self.multiplexer.indication(self, pdu)

    def service_confirmation(self, conn, pdu):
        raise NotImplementedError('service_confirmation must be overridden')
