
from ..debugging import DebugContents
from .constants import *

__all__ = ['UserInformation']


class UserInformation(DebugContents):
    """
    UserInformation
    """
    _debug_contents = ('username', 'password*', 'service', 'proxyNetwork')

    def __init__(self, **kwargs):
        # init from kwargs
        self.username = kwargs.get('username', None)
        self.password = kwargs.get('password', None)
        # init what services are available
        self.service = {}
        all_services = kwargs.get('allServices', False)
        self.service[DEVICE_TO_DEVICE_SERVICE_ID] = kwargs.get('deviceToDeviceService', all_services)
        self.service[ROUTER_TO_ROUTER_SERVICE_ID] = kwargs.get('routerToRouterService', all_services)
        self.service[PROXY_SERVICE_ID] = kwargs.get('proxyService', all_services)
        self.service[LANE_SERVICE_ID] = kwargs.get('laneService', all_services)
        self.service[CLIENT_SERVER_SERVICE_ID] = kwargs.get('clientServerService', all_services)
        # proxy service can map to a network
        self.proxyNetwork = kwargs.get('proxyNetwork', None)
