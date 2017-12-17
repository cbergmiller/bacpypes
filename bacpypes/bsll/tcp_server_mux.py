
import random
import logging

from ..comm import Client, bind
from ..transport import TCPServerDirector
from ..link import Address, PDU, unpack_ip_addr
from .registry import bsl_pdu_types, hash_functions
from .constants import *
from .bslci import *
from .bslpdu import *
from .connection_state import ConnectionState
from .tcp_mux_ase import TCPMultiplexerASE
from .utils import _StreamToPacket

_logger = logging.getLogger(__name__)
__all__ = ['TCPServerMultiplexer']


class TCPServerMultiplexer(Client):
    """
    TCPServerMultiplexer
    """

    def __init__(self, addr=None):
        Client.__init__(self)

        # check for some options
        if addr is None:
            self.address = Address()
            self.addrTuple = ('', 47808)
        else:
            # allow the address to be cast
            if isinstance(addr, Address):
                self.address = addr
            else:
                self.address = Address(addr)
            # extract the tuple for binding
            self.addrTuple = self.address.addrTuple

        # create and bind
        self.director = TCPServerDirector(self.addrTuple)
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
        super(TCPServerMultiplexer, self).request(ypdu)

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
            _logger.warning('no connection: %r', pdu.pduSource)
            return
        # extract the function for easy access
        fn = bslpdu.bslciFunction
        # get the class related to the function
        rpdu = bsl_pdu_types[fn]()
        rpdu.decode(bslpdu)
        # redirect
        if fn == BSLCI.result:
            _logger.warning('unexpected Result')
        # client is asking for a particular service
        elif fn == BSLCI.serviceRequest:
            # if it is already connected, disconnect it
            if conn.service and conn.connected:
                conn.service.remove_connection(conn)
            new_sap = None
            result_code = SUCCESS
            if rpdu.bslciServiceID == DEVICE_TO_DEVICE_SERVICE_ID:
                if self.deviceToDeviceService:
                    new_sap = self.deviceToDeviceService
                else:
                    result_code = NO_DEVICE_TO_DEVICE_SERVICE
            elif rpdu.bslciServiceID == ROUTER_TO_ROUTER_SERVICE_ID:
                if self.routerToRouterService:
                    new_sap = self.routerToRouterService
                else:
                    result_code = NO_ROUTER_TO_ROUTER_SERVICE
            elif rpdu.bslciServiceID == PROXY_SERVICE_ID:
                if self.proxyService:
                    new_sap = self.proxyService
                else:
                    result_code = NO_PROXY_SERVICE
            elif rpdu.bslciServiceID == LANE_SERVICE_ID:
                if self.laneService:
                    new_sap = self.laneService
                else:
                    result_code = NO_LANE_SERVICE
            else:
                result_code = UNRECOGNIZED_SERVICE
            # success means the service requested is supported
            if result_code:
                response = Result(result_code)
                response.pduDestination = rpdu.pduSource
                self.request(response)
                return
            # check to see if authentication is required
            if not new_sap.authentication_required(conn.address):
                new_sap.add_connection(conn)
            else:
                # if there is no userinfo, try to get default userinfo
                if not conn.userinfo:
                    conn.userinfo = new_sap.get_default_user_info(conn.address)
                    if conn.userinfo:
                        conn.accessState = ConnectionState.AUTHENTICATED
                # check if authentication has occurred
                if not conn.accessState == ConnectionState.AUTHENTICATED:
                    result_code = AUTHENTICATION_REQUIRED
                    # save a reference to the service to use when authenticated
                    conn.service = new_sap
                # make sure the user can use the service
                elif not conn.userinfo.service[new_sap.serviceID]:
                    result_code = AUTHENTICATION_NO_SERVICE
                # all's well
                else:
                    new_sap.add_connection(conn)
            response = Result(result_code)
            response.pduDestination = rpdu.pduSource
            self.request(response)
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
            if conn.service is not self.proxyService:
                _logger.warning('not connected to appropriate service')
                return
            self.proxyService.service_confirmation(conn, rpdu)
        elif (fn == BSLCI.proxyToServerBroadcastNPDU) and self.proxyService:
            if conn.service is not self.proxyService:
                _logger.warning('not connected to appropriate service')
                return
            self.proxyService.service_confirmation(conn, rpdu)
        elif (fn == BSLCI.serverToProxyUnicastNPDU) and self.proxyService:
            _logger.warning('unexpected Server-To-Proxy-Unicast-NPDU')
        elif (fn == BSLCI.serverToProxyBroadcastNPDU) and self.proxyService:
            _logger.warning('unexpected Server-To-Proxy-Broadcast-NPDU')
        elif (fn == BSLCI.clientToLESUnicastNPDU) and self.laneService:
            if conn.service is not self.laneService:
                _logger.warning('not connected to appropriate service')
                return
            self.laneService.service_confirmation(conn, rpdu)
        elif (fn == BSLCI.clientToLESBroadcastNPDU) and self.laneService:
            if conn.service is not self.laneService:
                _logger.warning('not connected to appropriate service')
                return
            self.laneService.service_confirmation(conn, rpdu)
        elif (fn == BSLCI.lesToClientUnicastNPDU) and self.laneService:
            _logger.warning('unexpected LES-to-Client-Unicast-NPDU')
        elif (fn == BSLCI.lesToClientBroadcastNPDU) and self.laneService:
            _logger.warning('unexpected LES-to-Client-Broadcast-NPDU')
        elif fn == BSLCI.accessRequest:
            self.do_AccessRequest(conn, rpdu)
        elif fn == BSLCI.accessChallenge:
            _logger.warning('unexpected Access-Challenge')
        elif fn == BSLCI.accessResponse:
            self.do_AccessResponse(conn, rpdu)
        else:
            _logger.warning('unsupported message')

    def do_AccessRequest(self, conn, bslpdu):
        # make sure this connection has requested a service first
        if not conn.service:
            response = Result(AUTHENTICATION_NO_SERVICE)
            response.pduDestination = bslpdu.pduSource
            self.request(response)
            return
        # make sure this process isn't being repeated more than once for the connection
        if conn.accessState != ConnectionState.NOT_AUTHENTICATED:
            # connection in the wrong state
            response = Result(AUTHENTICATION_FAILURE)
            response.pduDestination = bslpdu.pduSource
            self.request(response)
            return
        # get the hash function
        try:
            hash_fn = hash_functions[bslpdu.bslciHashFn]
        except:
            # no hash function
            response = Result(AUTHENTICATION_HASH)
            response.pduDestination = bslpdu.pduSource
            self.request(response)
            return
        # get the userinfo from the service
        conn.userinfo = conn.service.get_user_info(bslpdu.bslciUsername)
        if not conn.userinfo:
            # no user info
            response = Result(AUTHENTICATION_FAILURE)
            response.pduDestination = bslpdu.pduSource
            self.request(response)
            return
        # build a challenge string, save it in the connection
        challenge = hash_fn(''.join(chr(random.randrange(256)) for i in range(128)))
        conn.challenge = challenge
        # save that we have issued a challenge
        conn.accessState = ConnectionState.CHALLENGED
        # conn.userinfo is authentication information, build a challenge response and send it back
        response = AccessChallenge(bslpdu.bslciHashFn, challenge)
        response.pduDestination = conn.address
        self.request(response)

    def do_AccessResponse(self, conn, bslpdu):
        # start out happy
        result_code = SUCCESS
        # if there's no user, fail
        if not conn.userinfo:
            # connection has no user info
            result_code = AUTHENTICATION_FAILURE
        # make sure a challenge has been issued
        elif conn.accessState != ConnectionState.CHALLENGED:
            # connection in the wrong state
            result_code = AUTHENTICATION_FAILURE
        else:
            # get the hash function
            try:
                hash_fn = hash_functions[bslpdu.bslciHashFn]
            except:
                # no hash function
                response = Result(AUTHENTICATION_HASH)
                response.pduDestination = bslpdu.pduSource
                self.request(response)
                return
            # take the password, the challenge, and hash them
            challenge_response = hash_fn(conn.userinfo.password + conn.challenge)
            # see if the response matches what we think it should be
            if challenge_response == bslpdu.bslciResponse:
                # success
                # connection is now authenticated
                conn.accessState = ConnectionState.AUTHENTICATED
                # we may have gone through authentication without requesting a service
                if not conn.service:
                    # no service
                    pass
                # make sure the user can use the service
                elif not conn.userinfo.service[conn.service.serviceID]:
                    # break the reference to the service
                    result_code = AUTHENTICATION_NO_SERVICE
                    conn.service = None
                else:
                    # all's well
                    conn.service.add_connection(conn)
            else:
                # challenge/response mismatch
                result_code = AUTHENTICATION_FAILURE
        response = Result(result_code)
        response.pduDestination = bslpdu.pduSource
        self.request(response)
