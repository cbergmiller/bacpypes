
import logging

from .constants import *
from .service_adapter import ServiceAdapter
from .proxy_service_net_adapter import ProxyServiceNetworkAdapter

_logger = logging.getLogger(__name__)
__all__ = ['ProxyServerService']


class ProxyServerService(ServiceAdapter):
    """
    ProxyServerService
    """
    serviceID = PROXY_SERVICE_ID

    def __init__(self, mux, nsap):
        ServiceAdapter.__init__(self, mux)

        # save a reference to the network service access point
        self.nsap = nsap

    def add_connection(self, conn):
        # add as usual
        ServiceAdapter.add_connection(self, conn)
        # create a proxy adapter
        conn.proxyAdapter = ProxyServiceNetworkAdapter(conn, self.nsap, conn.userinfo.proxyNetwork)

    def remove_connection(self, conn):
        # remove as usual
        ServiceAdapter.remove_connection(self, conn)
        # remove the adapter from the list of adapters for the nsap
        self.nsap.adapters.remove(conn.proxyAdapter)

    def service_confirmation(self, conn, bslpdu):
        """Receive packets forwarded by the proxy and redirect them to the proxy network adapter."""
        # make sure there is an adapter for it - or something went wrong
        if not getattr(conn, 'proxyAdapter', None):
            raise RuntimeError('service confirmation received but no adapter for it')
        # forward along
        conn.proxyAdapter.service_confirmation(bslpdu)

