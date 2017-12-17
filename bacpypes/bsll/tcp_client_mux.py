
import logging

from ..comm import Client, bind
from ..transport import TCPClientDirector
from ..link import Address, PDU, unpack_ip_addr
from .registry import bsl_pdu_types, hash_functions
from .constants import *
from .bslci import *
from .bslpdu import *
from .connection_state import ConnectionState
from .tcp_mux_ase import TCPMultiplexerASE
from .utils import _StreamToPacket

_logger = logging.getLogger(__name__)
__all__ = ['TCPClientMultiplexer']


class TCPClientMultiplexer(Client):
    """
    TCPClientMultiplexer
    """

    def __init__(self):
        Client.__init__(self)
        # create and bind
        self.director = TCPClientDirector()
        bind(self, _StreamToPacket(), self.director)
        # create an application service element and bind
        self.ase = TCPMultiplexerASE(self)
        bind(self.ase, self.director)
        # keep a dictionary of connections
        self.connections = {}
        # no services available until they are created, they are
        # instances of ServiceAdapter
        self.deviceToDeviceService = None
        self.routerToRouterService = None
        self.proxyService = None
        self.laneService = None

    def request(self, pdu):
        # encode it as a BSLPDU
        xpdu = BSLPDU()
        pdu.encode(xpdu)
        # encode it as a raw PDU
        ypdu = PDU()
        xpdu.encode(ypdu)
        ypdu.pduDestination = unpack_ip_addr(pdu.pduDestination.addrAddr)
        # continue along
        super(TCPClientMultiplexer, self).request(ypdu)

    def indication(self, server, pdu):
        # pass through, it will be encoded
        self.request(pdu)

    def confirmation(self, pdu):
        # recast from a comm.PDU to a BACpypes PDU
        pdu = PDU(pdu, source=Address(pdu.pduSource))
        # interpret as a BSLL PDU
        bslpdu = BSLPDU()
        bslpdu.decode(pdu)
        # get the connection
        conn = self.connections.get(pdu.pduSource, None)
        if not conn:
            _logger.warning(f'no connection: {pdu.pduSource!r}')
            return
        # extract the function for easy access
        fn = bslpdu.bslciFunction
        # get the class related to the function
        rpdu = bsl_pdu_types[fn]()
        rpdu.decode(bslpdu)
        # redirect
        if fn == BSLCI.result:
            # if the connection is not associated with a service, toss it
            if not conn.service:
                _logger.warning('unexpected result')
                return
            # if it is already connected, stop
            if conn.connected:
                _logger.warning('unexpected result, already connected')
                return
            # if this is successful, add it to the service
            if rpdu.bslciResultCode == SUCCESS:
                # if authentication was required, change to authenticate when this ack comes back
                if conn.accessState == ConnectionState.REQUESTED:
                    # authentication successful
                    conn.accessState = ConnectionState.AUTHENTICATED
                # add the connection to the service
                conn.service.add_connection(conn)
                # let the service process the ack
                conn.service.connect_ack(conn, rpdu)
            # if authentication is required, start the process
            elif rpdu.bslciResultCode == AUTHENTICATION_REQUIRED:
                # make sure this process isn't being repeated more than once for the connection
                if conn.accessState != ConnectionState.NOT_AUTHENTICATED:
                    _logger.warning('unexpected authentication required')
                    return
                conn.userinfo = conn.service.get_default_user_info(conn.address)
                if not conn.userinfo:
                    _logger.warning('authentication required, no user information')
                    return
                # set the connection state
                conn.accessState = ConnectionState.REQUESTED
                # send the username
                response = AccessRequest(0, conn.userinfo.username)
                response.pduDestination = rpdu.pduSource
                self.request(response)
            else:
                _logger.warning(f'result code: {rpdu.bslciResultCode!r}')
        elif fn == BSLCI.serviceRequest:
            _logger.warning('unexpected service request')
        elif (fn == BSLCI.deviceToDeviceAPDU) and self.deviceToDeviceService:
            if conn.service is not self.deviceToDeviceService:
                _logger.warning('not connected to appropriate service')
                return
            self.deviceToDeviceService.service_confirmation(conn, rpdu)
        elif (fn == BSLCI.routerToRouterNPDU) and self.routerToRouterService:
            if conn.service is not self.routerToRouterService:
                _logger.warning('not connected to appropriate service')
                return
            self.routerToRouterService.service_confirmation(conn, rpdu)
        elif (fn == BSLCI.proxyToServerUnicastNPDU) and self.proxyService:
            _logger.warning('unexpected Proxy-To-Server-Unicast-NPDU')
        elif (fn == BSLCI.proxyToServerBroadcastNPDU) and self.proxyService:
            _logger.warning('unexpected Proxy-To-Broadcast-Unicast-NPDU')
        elif (fn == BSLCI.serverToProxyUnicastNPDU) and self.proxyService:
            if conn.service is not self.proxyService:
                _logger.warning('not connected to appropriate service')
                return
            self.proxyService.service_confirmation(conn, rpdu)
        elif (fn == BSLCI.serverToProxyBroadcastNPDU) and self.proxyService:
            if conn.service is not self.proxyService:
                _logger.warning('not connected to appropriate service')
                return
            self.proxyService.service_confirmation(conn, rpdu)
        elif (fn == BSLCI.clientToLESUnicastNPDU) and self.laneService:
            _logger.warning('unexpected Client-to-LES-Unicast-NPDU')
        elif (fn == BSLCI.clientToLESBroadcastNPDU) and self.laneService:
            _logger.warning('unexpected Client-to-LES-Broadcast-NPDU')
        elif (fn == BSLCI.lesToClientUnicastNPDU) and self.laneService:
            if conn.service is not self.laneService:
                _logger.warning('not connected to appropriate service')
                return
            self.laneService.service_confirmation(conn, rpdu)
        elif (fn == BSLCI.lesToClientBroadcastNPDU) and self.laneService:
            if conn.service is not self.laneService:
                _logger.warning('not connected to appropriate service')
                return
            self.laneService.service_confirmation(conn, rpdu)
        elif fn == BSLCI.accessRequest:
            _logger.warning('unexpected Access-request')
        elif fn == BSLCI.accessChallenge:
            self.do_AccessChallenge(conn, rpdu)
        elif fn == BSLCI.accessResponse:
            _logger.warning('unexpected Access-response')
        else:
            _logger.warning('unsupported message: %s', rpdu.__class__.__name__)

    def do_AccessChallenge(self, conn, bslpdu):
        # make sure this process isn't being repeated more than once for the connection
        if conn.accessState != ConnectionState.REQUESTED:
            _logger.warning('unexpected access challenge')
            return
        # get the hash function
        try:
            hash_fn = hash_functions[bslpdu.bslciHashFn]
        except Exception:
            _logger.warning('no hash function: %r', bslpdu.bslciHashFn)
            return
        # take the password, the challenge, and hash them
        challenge_response = hash_fn(conn.userinfo.password + bslpdu.bslciChallenge)
        # conn.userinfo is authentication information, build a challenge response and send it back
        response = AccessResponse(bslpdu.bslciHashFn, challenge_response)
        response.pduDestination = conn.address
        self.request(response)
