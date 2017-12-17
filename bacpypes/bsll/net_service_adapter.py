
import logging

from ..network import NetworkAdapter
from .service_adapter import ServiceAdapter

_logger = logging.getLogger(__name__)
__all__ = ['NetworkServiceAdapter']


class NetworkServiceAdapter(ServiceAdapter, NetworkAdapter):
    """
    NetworkServiceAdapter
    """

    def __init__(self, mux, sap, net, cid=None):
        ServiceAdapter.__init__(self, mux)
        NetworkAdapter.__init__(self, sap, net, cid)
