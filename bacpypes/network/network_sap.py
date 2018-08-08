
import logging
from copy import deepcopy as _deepcopy

from .netservice import NetworkAdapter, RouterInfo, RouterInfoCache
from ..debugging import DebugContents
from ..errors import ConfigurationError
from ..comm import Server, bind, ServiceAccessPoint
from ..link import Address, LocalBroadcast, LocalStation, RemoteStation
from .npdu import NPDU, WhoIsRouterToNetwork, npdu_types
from ..apdu import APDU as _APDU

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['NetworkServiceAccessPoint']


class NetworkServiceAccessPoint(ServiceAccessPoint, Server, DebugContents):

    DEBUG_contents = ('adapters++', 'routers++', 'networks+', 'localAdapter-', 'localAddress')

    def __init__(self, routerInfoCache=None, sap=None, sid=None):
        if DEBUG: _logger.debug("__init__ sap=%r sid=%r", sap, sid)
        ServiceAccessPoint.__init__(self, sap)
        Server.__init__(self, sid)

        # map of directly connected networks
        self.adapters = {}          # net -> NetworkAdapter

        # use the provided cache or make a default one
        self.router_info_cache = routerInfoCache or RouterInfoCache()

        # map to a list of application layer packets waiting for a path
        self.pending_nets = {}

        # these are set when bind() is called
        self.local_adapter = None
        self.local_address = None

    def bind(self, server, net=None, address=None):
        """Create a network adapter object and bind."""
        if DEBUG: _logger.debug("bind %r net=%r address=%r", server, net, address)

        # make sure this hasn't already been called with this network
        if net in self.adapters:
            raise RuntimeError("already bound")

        # when binding to an adapter and there is more than one, then they
        # must all have network numbers and one of them will be the default
        if (net is not None) and (None in self.adapters):
            raise RuntimeError("default adapter bound")

        # create an adapter object, add it to our map
        adapter = NetworkAdapter(self, net)
        self.adapters[net] = adapter
        if DEBUG: _logger.debug("    - adapters[%r]: %r", net, adapter)

        # if the address was given, make it the "local" one
        if address:
            self.local_adapter = adapter
            self.local_address = address

        # bind to the server
        bind(adapter, server)

    #-----

    def add_router_references(self, snet, address, dnets):
        """Add/update references to routers."""
        if DEBUG: _logger.debug("add_router_references %r %r %r", snet, address, dnets)

        # see if we have an adapter for the snet
        if snet not in self.adapters:
            raise RuntimeError("no adapter for network: %d" % (snet,))

        # pass this along to the cache
        self.router_info_cache.update_router_info(snet, address, dnets)

    def delete_router_references(self, snet, address=None, dnets=None):
        """Delete references to routers/networks."""
        if DEBUG: _logger.debug("delete_router_references %r %r %r", snet, address, dnets)

        # see if we have an adapter for the snet
        if snet not in self.adapters:
            raise RuntimeError("no adapter for network: %d" % (snet,))

        # pass this along to the cache
        self.router_info_cache.delete_router_info(snet, address, dnets)

    #-----

    def indication(self, pdu):
        if DEBUG: _logger.debug("indication %r", pdu)

        # make sure our configuration is OK
        if (not self.adapters):
            raise ConfigurationError("no adapters")

        # might be able to relax this restriction
        if (len(self.adapters) > 1) and (not self.local_adapter):
            raise ConfigurationError("local adapter must be set")

        # get the local adapter
        adapter = self.local_adapter or self.adapters[None]
        if DEBUG: _logger.debug("    - adapter: %r", adapter)

        # build a generic APDU
        apdu = _APDU(user_data=pdu.pduUserData)
        pdu.encode(apdu)
        if DEBUG: _logger.debug("    - apdu: %r", apdu)

        # build an NPDU specific to where it is going
        npdu = NPDU(user_data=pdu.pduUserData)
        apdu.encode(npdu)
        if DEBUG: _logger.debug("    - npdu: %r", npdu)

        # the hop count always starts out big
        npdu.npduHopCount = 255

        # local stations given to local adapter
        if (npdu.pduDestination.addrType == Address.localStationAddr):
            adapter.process_npdu(npdu)
            return

        # local broadcast given to local adapter
        if (npdu.pduDestination.addrType == Address.localBroadcastAddr):
            adapter.process_npdu(npdu)
            return

        # global broadcast
        if (npdu.pduDestination.addrType == Address.globalBroadcastAddr):
            # set the destination
            npdu.pduDestination = LocalBroadcast()
            npdu.npduDADR = apdu.pduDestination

            # send it to all of connected adapters
            for xadapter in self.adapters.values():
                xadapter.process_npdu(npdu)
            return

        # remote broadcast
        if (npdu.pduDestination.addrType != Address.remoteBroadcastAddr) and (npdu.pduDestination.addrType != Address.remoteStationAddr):
            raise RuntimeError("invalid destination address type: %s" % (npdu.pduDestination.addrType,))

        dnet = npdu.pduDestination.addrNet

        # if the network matches the local adapter it's local
        if (dnet == adapter.adapterNet):
            ### log this, the application shouldn't be sending to a remote station address
            ### when it's a directly connected network
            raise RuntimeError("addressing problem")

        # get it ready to send when the path is found
        npdu.pduDestination = None
        npdu.npduDADR = apdu.pduDestination

        # we might already be waiting for a path for this network
        if dnet in self.pending_nets:
            if DEBUG: _logger.debug("    - already waiting for path")
            self.pending_nets[dnet].append(npdu)
            return

        # check cache for an available path
        path_info = self.router_info_cache.get_router_info(dnet)

        # if there is info, we have a path
        if path_info:
            snet, address, status = path_info
            if DEBUG: _logger.debug("    - path found: %r, %r, %r", snet, address, status)

            # check for an adapter
            if snet not in self.adapters:
                raise RuntimeError("network found but not connected: %r", snet)
            adapter = self.adapters[snet]
            if DEBUG: _logger.debug("    - adapter: %r", adapter)

            # fix the destination
            npdu.pduDestination = address

            # send it along
            adapter.process_npdu(npdu)
            return

        if DEBUG: _logger.debug("    - no known path to network")

        # add it to the list of packets waiting for the network
        net_list = self.pending_nets.get(dnet, None)
        if net_list is None:
            net_list = self.pending_nets[dnet] = []
        net_list.append(npdu)

        # build a request for the network and send it to all of the adapters
        xnpdu = WhoIsRouterToNetwork(dnet)
        xnpdu.pduDestination = LocalBroadcast()

        # send it to all of the connected adapters
        for adapter in self.adapters.values():
            ### make sure the adapter is OK
            self.sap_indication(adapter, xnpdu)

    def process_npdu(self, adapter, npdu):
        if DEBUG: _logger.debug("process_npdu %r %r", adapter, npdu)

        # make sure our configuration is OK
        if (not self.adapters):
            raise ConfigurationError("no adapters")

        # check for source routing
        if npdu.npduSADR and (npdu.npduSADR.addrType != Address.nullAddr):
            if DEBUG: _logger.debug("    - check source path")

            # see if this is attempting to spoof a directly connected network
            snet = npdu.npduSADR.addrNet
            if snet in self.adapters:
                _logger.warning("    - path error (1)")
                return

            # see if there is routing information for this source network
            router_info = self.router_info_cache.get_router_info(snet)
            if router_info:
                router_snet, router_address, router_status = router_info
                if DEBUG: _logger.debug("    - router_address, router_status: %r, %r", router_address, router_status)

                # see if the router has changed
                if not (router_address == npdu.pduSource):
                    if DEBUG: _logger.debug("    - replacing path")

                    # pass this new path along to the cache
                    self.router_info_cache.update_router_info(adapter.adapterNet, npdu.pduSource, [snet])
            else:
                if DEBUG: _logger.debug("    - new path")

                # pass this new path along to the cache
                self.router_info_cache.update_router_info(adapter.adapterNet, npdu.pduSource, [snet])

        # check for destination routing
        if (not npdu.npduDADR) or (npdu.npduDADR.addrType == Address.nullAddr):
            if DEBUG: _logger.debug("    - no DADR")

            processLocally = (not self.local_adapter) or (adapter is self.local_adapter) or (npdu.npduNetMessage is not None)
            forwardMessage = False

        elif npdu.npduDADR.addrType == Address.remoteBroadcastAddr:
            if DEBUG: _logger.debug("    - DADR is remote broadcast")

            if (npdu.npduDADR.addrNet == adapter.adapterNet):
                _logger.warning("    - path error (2)")
                return

            processLocally = self.local_adapter \
                and (npdu.npduDADR.addrNet == self.local_adapter.adapterNet)
            forwardMessage = True

        elif npdu.npduDADR.addrType == Address.remoteStationAddr:
            if DEBUG: _logger.debug("    - DADR is remote station")

            if (npdu.npduDADR.addrNet == adapter.adapterNet):
                _logger.warning("    - path error (3)")
                return

            processLocally = self.local_adapter \
                and (npdu.npduDADR.addrNet == self.local_adapter.adapterNet) \
                and (npdu.npduDADR.addrAddr == self.local_address.addrAddr)
            forwardMessage = not processLocally

        elif npdu.npduDADR.addrType == Address.globalBroadcastAddr:
            if DEBUG: _logger.debug("    - DADR is global broadcast")

            processLocally = True
            forwardMessage = True

        else:
            _logger.warning("invalid destination address type: %s", npdu.npduDADR.addrType)
            return

        if DEBUG:
            _logger.debug("    - processLocally: %r", processLocally)
            _logger.debug("    - forwardMessage: %r", forwardMessage)

        # application or network layer message
        if npdu.npduNetMessage is None:
            if DEBUG: _logger.debug("    - application layer message")

            if processLocally and self.serverPeer:
                if DEBUG: _logger.debug("    - processing APDU locally")

                # decode as a generic APDU
                apdu = _APDU(user_data=npdu.pduUserData)
                apdu.decode(_deepcopy(npdu))
                if DEBUG: _logger.debug("    - apdu: %r", apdu)

                # see if it needs to look routed
                if (len(self.adapters) > 1) and (adapter != self.local_adapter):
                    # combine the source address
                    if not npdu.npduSADR:
                        apdu.pduSource = RemoteStation( adapter.adapterNet, npdu.pduSource.addrAddr )
                    else:
                        apdu.pduSource = npdu.npduSADR

                    # map the destination
                    if not npdu.npduDADR:
                        apdu.pduDestination = self.local_address
                    elif npdu.npduDADR.addrType == Address.globalBroadcastAddr:
                        apdu.pduDestination = npdu.npduDADR
                    elif npdu.npduDADR.addrType == Address.remoteBroadcastAddr:
                        apdu.pduDestination = LocalBroadcast()
                    else:
                        apdu.pduDestination = self.localAddress
                else:
                    # combine the source address
                    if npdu.npduSADR:
                        apdu.pduSource = npdu.npduSADR
                    else:
                        apdu.pduSource = npdu.pduSource

                    # pass along global broadcast
                    if npdu.npduDADR and npdu.npduDADR.addrType == Address.globalBroadcastAddr:
                        apdu.pduDestination = npdu.npduDADR
                    else:
                        apdu.pduDestination = npdu.pduDestination
                if DEBUG:
                    _logger.debug("    - apdu.pduSource: %r", apdu.pduSource)
                    _logger.debug("    - apdu.pduDestination: %r", apdu.pduDestination)

                # pass upstream to the application layer
                self.response(apdu)

        else:
            if DEBUG: _logger.debug("    - network layer message")

            if processLocally:
                if npdu.npduNetMessage not in npdu_types:
                    if DEBUG: _logger.debug("    - unknown npdu type: %r", npdu.npduNetMessage)
                    return

                if DEBUG: _logger.debug("    - processing NPDU locally")

                # do a deeper decode of the NPDU
                xpdu = npdu_types[npdu.npduNetMessage](user_data=npdu.pduUserData)
                xpdu.decode(_deepcopy(npdu))

                # pass to the service element
                self.sap_request(adapter, xpdu)

        # might not need to forward this to other devices
        if not forwardMessage:
            if DEBUG: _logger.debug("    - no forwarding")
            return

        # make sure we're really a router
        if (len(self.adapters) == 1):
            if DEBUG: _logger.debug("    - not a router")
            return

        # make sure it hasn't looped
        if (npdu.npduHopCount == 0):
            if DEBUG: _logger.debug("    - no more hops")
            return

        # build a new NPDU to send to other adapters
        newpdu = _deepcopy(npdu)

        # clear out the source and destination
        newpdu.pduSource = None
        newpdu.pduDestination = None

        # decrease the hop count
        newpdu.npduHopCount -= 1

        # set the source address
        if not npdu.npduSADR:
            newpdu.npduSADR = RemoteStation( adapter.adapterNet, npdu.pduSource.addrAddr )
        else:
            newpdu.npduSADR = npdu.npduSADR

        # if this is a broadcast it goes everywhere
        if npdu.npduDADR.addrType == Address.globalBroadcastAddr:
            if DEBUG: _logger.debug("    - global broadcasting")
            newpdu.pduDestination = LocalBroadcast()

            for xadapter in self.adapters.values():
                if (xadapter is not adapter):
                    xadapter.process_npdu(_deepcopy(newpdu))
            return

        if (npdu.npduDADR.addrType == Address.remoteBroadcastAddr) \
                or (npdu.npduDADR.addrType == Address.remoteStationAddr):
            dnet = npdu.npduDADR.addrNet
            if DEBUG: _logger.debug("    - remote station/broadcast")

            # see if this a locally connected network
            if dnet in self.adapters:
                xadapter = self.adapters[dnet]
                if xadapter is adapter:
                    if DEBUG: _logger.debug("    - path error (4)")
                    return
                if DEBUG: _logger.debug("    - found path via %r", xadapter)

                # if this was a remote broadcast, it's now a local one
                if (npdu.npduDADR.addrType == Address.remoteBroadcastAddr):
                    newpdu.pduDestination = LocalBroadcast()
                else:
                    newpdu.pduDestination = LocalStation(npdu.npduDADR.addrAddr)

                # last leg in routing
                newpdu.npduDADR = None

                # send the packet downstream
                xadapter.process_npdu(_deepcopy(newpdu))
                return

            # see if there is routing information for this destination network
            router_info = self.router_info_cache.get_router_info(dnet)
            if router_info:
                router_net, router_address, router_status = router_info
                if DEBUG: _logger.debug(
                    "    - router_net, router_address, router_status: %r, %r, %r",
                    router_net, router_address, router_status,
                    )

                if router_net not in self.adapters:
                    if DEBUG: _logger.debug("    - path error (5)")
                    return

                xadapter = self.adapters[router_net]
                if DEBUG: _logger.debug("    - found path via %r", xadapter)

                # the destination is the address of the router
                newpdu.pduDestination = router_address

                # send the packet downstream
                xadapter.process_npdu(_deepcopy(newpdu))
                return

            if DEBUG: _logger.debug("    - no router info found")

            ### queue this message for reprocessing when the response comes back

            # try to find a path to the network
            xnpdu = WhoIsRouterToNetwork(dnet)
            xnpdu.pduDestination = LocalBroadcast()

            # send it to all of the connected adapters
            for xadapter in self.adapters.values():
                # skip the horse it rode in on
                if (xadapter is adapter):
                    continue

                # pass this along as if it came from the NSE
                self.sap_indication(xadapter, xnpdu)

            return

        if DEBUG: _logger.debug("    - bad DADR: %r", npdu.npduDADR)

    def sap_indication(self, adapter, npdu):
        if DEBUG: _logger.debug("sap_indication %r %r", adapter, npdu)

        # encode it as a generic NPDU
        xpdu = NPDU(user_data=npdu.pduUserData)
        npdu.encode(xpdu)
        npdu._xpdu = xpdu

        # tell the adapter to process the NPDU
        adapter.process_npdu(xpdu)

    def sap_confirmation(self, adapter, npdu):
        if DEBUG: _logger.debug("sap_confirmation %r %r", adapter, npdu)

        # encode it as a generic NPDU
        xpdu = NPDU(user_data=npdu.pduUserData)
        npdu.encode(xpdu)
        npdu._xpdu = xpdu

        # tell the adapter to process the NPDU
        adapter.process_npdu(xpdu)
