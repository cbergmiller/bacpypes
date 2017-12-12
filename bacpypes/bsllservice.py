#!/usr/bin/python

"""
BACnet Streaming Link Layer Service
"""

import random
import logging
from .debugging import ModuleLogger, DebugContents, bacpypes_debugging

from .comm import Client, bind, ApplicationServiceElement
from .tcp import TCPClientDirector, TCPServerDirector, StreamToPacket

from .pdu import Address, LocalBroadcast, PDU, unpack_ip_addr
from .npdu import NPDU
from .netservice import NetworkAdapter

from .bsll import AUTHENTICATION_FAILURE, AUTHENTICATION_HASH, \
    AUTHENTICATION_NO_SERVICE, AUTHENTICATION_REQUIRED, AccessChallenge, \
    AccessRequest, AccessResponse, BSLCI, BSLPDU, \
    CLIENT_SERVER_SERVICE_ID, DEVICE_TO_DEVICE_SERVICE_ID, DeviceToDeviceAPDU, \
    LANE_SERVICE_ID, NO_DEVICE_TO_DEVICE_SERVICE, \
    NO_LANE_SERVICE, NO_PROXY_SERVICE, NO_ROUTER_TO_ROUTER_SERVICE, \
    PROXY_SERVICE_ID, ProxyToServerBroadcastNPDU, ProxyToServerUnicastNPDU, \
    ROUTER_TO_ROUTER_SERVICE_ID, Result, RouterToRouterNPDU, SUCCESS, \
    ServerToProxyBroadcastNPDU, ServerToProxyUnicastNPDU, ServiceRequest, \
    UNRECOGNIZED_SERVICE, bsl_pdu_types, hash_functions

_logger = logging.getLogger(__name__)


def _Packetize(data):
    """
    _Packetize
    """
    # look for the type field
    start_ind = data.find('\x83')
    if start_ind == -1:
        return None
    # chop off everything up to the start, it's garbage
    if start_ind > 0:
        data = data[start_ind:]
    # make sure we have at least a complete header
    if len(data) < 4:
        return None
    # get the length, make sure we have the whole packet
    total_len = (ord(data[2]) << 8) + ord(data[3])
    if len(data) < total_len:
        return None
    packet_slice = (data[:total_len], data[total_len:])
    return packet_slice


class _StreamToPacket(StreamToPacket):
    """
    _StreamToPacket
    """
    def __init__(self):
        super(_StreamToPacket, self).__init__(_Packetize)

    def indication(self, pdu):
        self.request(pdu)


class UserInformation(DebugContents):
    """
    UserInformation
    """

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


class ConnectionState(DebugContents):
    """
    ConnectionState
    """
    NOT_AUTHENTICATED   = 0     # no authentication attempted
    REQUESTED           = 1     # access request sent to the server (client only)
    CHALLENGED          = 2     # access challenge sent to the client (server only)
    AUTHENTICATED       = 3     # authentication successful

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
            _logger.warning(f'remove_connection: {conn!r} not a connection')
        # clear out the connection attributes
        conn.service = None
        conn.connected = False

    def service_request(self, pdu):
        # direct requests to the multiplexer
        self.multiplexer.indication(self, pdu)

    def service_confirmation(self, conn, pdu):
        raise NotImplementedError('service_confirmation must be overridden')


class NetworkServiceAdapter(ServiceAdapter, NetworkAdapter):
    """
    NetworkServiceAdapter
    """
    def __init__(self, mux, sap, net, cid=None):
        ServiceAdapter.__init__(self, mux)
        NetworkAdapter.__init__(self, sap, net, cid)


class TCPServerMultiplexer(Client):
    """
    TCPServerMultiplexer
    """
    def __init__(self, addr=None):
        super(TCPServerMultiplexer, self).__init__()

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
            _logger.warning(f'no connection: {pdu.pduSource!r}')
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

#
#   
#

class TCPClientMultiplexer(Client):
    """
    TCPClientMultiplexer
    """
    def __init__(self):
        super(TCPClientMultiplexer, self).__init__()
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
            _logger.warning(f'unsupported message: {rpdu.__class__.__name__}')

    def do_AccessChallenge(self, conn, bslpdu):
        # make sure this process isn't being repeated more than once for the connection
        if conn.accessState != ConnectionState.REQUESTED:
            _logger.warning('unexpected access challenge')
            return
        # get the hash function
        try:
            hash_fn = hash_functions[bslpdu.bslciHashFn]
        except Exception:
            _logger.warning(f'no hash function: {bslpdu.bslciHashFn!r}')
            return
        # take the password, the challenge, and hash them
        challenge_response = hash_fn(conn.userinfo.password + bslpdu.bslciChallenge)
        # conn.userinfo is authentication information, build a challenge response and send it back
        response = AccessResponse(bslpdu.bslciHashFn, challenge_response)
        response.pduDestination = conn.address
        self.request(response)


class TCPMultiplexerASE(ApplicationServiceElement):
    """
    TCPMultiplexerASE
    """
    def __init__(self, mux):
        # keep track of the multiplexer
        self.multiplexer = mux
        # ToDo: why is the call to __init__ of the base class missing here?

    def indication(self, *args, **kwargs):
        if 'addPeer' in kwargs:
            addr = Address(kwargs['addPeer'])
            if addr in self.multiplexer.connections:
                # already a connection
                return
            conn = ConnectionState(addr)
            # add it to the multiplexer connections
            self.multiplexer.connections[addr] = conn

        if 'delPeer' in kwargs:
            addr = Address(kwargs['delPeer'])
            if addr not in self.multiplexer.connections:
                # not a connection
                return
            # get the connection
            conn = self.multiplexer.connections.get(addr)
            # if it is associated and connected, disconnect it
            if conn.service and conn.connected:
                conn.service.remove_connection(conn)
            # remove it from the multiplexer
            del self.multiplexer.connections[addr]


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


class RouterToRouterService(NetworkServiceAdapter):
    """
    RouterToRouterService
    """
    serviceID = ROUTER_TO_ROUTER_SERVICE_ID

    def process_npdu(self, npdu):
        """encode NPDUs from the service access point and send them downstream."""
        # encode the npdu as if it was about to be delivered to the network
        pdu = PDU()
        npdu.encode(pdu)
        # broadcast messages go to everyone
        if pdu.pduDestination.addrType == Address.localBroadcastAddr:
            dest_list = self.connections.keys()
        else:
            conn = self.connections.get(pdu.pduDestination, None)
            if not conn:
                # not a connected client
                # start a connection attempt
                conn = self.connect(pdu.pduDestination)
            if not conn.connected:
                # keep a reference to this pdu to send after the ack comes back
                conn.pendingNPDU.append(pdu)
                return
            dest_list = [pdu.pduDestination]
        for dest in dest_list:
            # make a router-to-router NPDU
            xpdu = RouterToRouterNPDU(pdu)
            xpdu.pduDestination = dest

            # send it to the multiplexer
            self.service_request(xpdu)

    def connect(self, addr):
        """Initiate a connection request to the peer router."""
        # make a connection
        conn = ConnectionState(addr)
        self.multiplexer.connections[addr] = conn
        # associate with this service, but it is not connected until the ack comes back
        conn.service = self
        # keep a list of pending NPDU objects until the ack comes back
        conn.pendingNPDU = []
        # build a service request
        request = ServiceRequest(ROUTER_TO_ROUTER_SERVICE_ID)
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
                    # make router-to-router NPDU
                    xpdu = RouterToRouterNPDU(npdu)
                    xpdu.pduDestination = npdu.pduDestination
                    # send it down to the multiplexer
                    self.service_request(xpdu)
                conn.pendingNPDU = []
        else:
            pass

    def add_connection(self, conn):
        # first do the usual things
        NetworkServiceAdapter.add_connection(self, conn)
        # generate a Who-Is-Router-To-Network, all networks
        # send it to the client

    def remove_connection(self, conn):
        # first to the usual thing
        NetworkServiceAdapter.remove_connection(self, conn)
        # the NSAP needs routing table information related to this connection flushed
        self.adapterSAP.remove_router_references(self, conn.address)

    def service_confirmation(self, conn, pdu):
        # decode it, the nework layer needs NPDUs
        npdu = NPDU()
        npdu.decode(pdu)
        npdu.pduSource = pdu.pduSource
        # send it to the service access point for processing
        self.adapterSAP.process_npdu(self, npdu)


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


class ProxyServerService(ServiceAdapter):
    """
    ProxyServerService
    """
    serviceID = PROXY_SERVICE_ID

    def __init__(self, mux, nsap):
        super(ProxyServerService, self).__init__(mux)
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
            _logger.warning(f'connection nack: {bslpdu.bslciResultCode!r}')

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
