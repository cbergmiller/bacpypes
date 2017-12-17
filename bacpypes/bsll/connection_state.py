
from ..debugging import DebugContents

__all__ = ['ConnectionState']


class ConnectionState(DebugContents):
    """
    ConnectionState
    """
    _debug_contents = ('address', 'service', 'connected', 'accessState', 'challenge', 'userinfo', 'proxyAdapter')

    NOT_AUTHENTICATED = 0  # no authentication attempted
    REQUESTED = 1  # access request sent to the server (client only)
    CHALLENGED = 2  # access challenge sent to the client (server only)
    AUTHENTICATED = 3  # authentication successful

    def __init__(self, addr):
        # save the address
        self.address = addr
        # this is not associated with a specific service
        self.service = None
        # start out disconnected until the service request is acked
        self.connected = False
        # access information
        self.accessState = ConnectionState.NOT_AUTHENTICATED
        self.challenge = None
        self.userinfo = None
        # reference to adapter used by proxy server service
        self.proxyAdapter = None