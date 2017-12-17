
import logging
from copy import copy as _copy

from .netservice import NetworkAdapter, RouterReference
from ..debugging import DebugContents
from ..errors import ConfigurationError
from ..comm import Server, bind, ServiceAccessPoint
from ..link import Address, LocalBroadcast, LocalStation, RemoteStation
from .npdu import NPDU, WhoIsRouterToNetwork, npdu_types
from ..apdu import APDU as _APDU

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['NetworkServiceAccessPoint']


class NetworkServiceAccessPoint(ServiceAccessPoint, Server, DebugContents):

    _debug_contents = (
        'adapters++', 'routers++', 'networks+', 'localAdapter-', 'localAddress'
    )

    def __init__(self, sap=None, sid=None):
        if DEBUG: _logger.debug('__init__ sap=%r sid=%r', sap, sid)
        ServiceAccessPoint.__init__(self, sap)
        Server.__init__(self, sid)
        self.adapters = []          # list of adapters
        self.routers = {}           # (adapter, address) -> RouterReference
        self.networks = {}          # network -> RouterReference
        self.localAdapter = None    # which one is local
        self.localAddress = None    # what is the local address

    def bind(self, server, net=None, address=None):
        """Create a network adapter object and bind."""
        if DEBUG: _logger.debug('bind %r net=%r address=%r', server, net, address)
        if (net is None) and self.adapters:
            raise RuntimeError('already bound')
        # create an adapter object
        adapter = NetworkAdapter(self, net)
        # if the address was given, make it the "local" one
        if address:
            self.localAdapter = adapter
            self.localAddress = address
        # bind to the server
        bind(adapter, server)

    def add_router_references(self, adapter, address, netlist):
        """Add/update references to routers."""
        if DEBUG: _logger.debug('add_router_references %r %r %r', adapter, address, netlist)
        # make a key for the router reference
        rkey = (adapter, address)
        for snet in netlist:
            # see if this is spoofing an existing routing table entry
            if snet in self.networks:
                rref = self.networks[snet]
                if rref.adapter == adapter and rref.address == address:
                    pass        # matches current entry
                else:
                    ### check to see if this source could be a router to the new network
                    # remove the network from the rref
                    i = rref.networks.index(snet)
                    del rref.networks[i]
                    # remove the network
                    del self.networks[snet]
            ### check to see if it is OK to add the new entry
            # get the router reference for this router
            rref = self.routers.get(rkey, None)
            if rref:
                if snet not in rref.networks:
                    # add the network
                    rref.networks.append(snet)
                    # reference the snet
                    self.networks[snet] = rref
            else:
                # new reference
                rref = RouterReference( adapter, address, [snet], 0)
                self.routers[rkey] = rref
                # reference the snet
                self.networks[snet] = rref

    def remove_router_references(self, adapter, address=None):
        """Add/update references to routers."""
        if DEBUG: _logger.debug('remove_router_references %r %r', adapter, address)
        delrlist = []
        delnlist = []
        # scan through the dictionary of router references
        for rkey in self.routers.keys():
            # rip apart the key
            radapter, raddress = rkey
            # pick all references on the adapter, optionally limited to a specific address
            match = radapter is adapter
            if match and address is not None:
                match = (raddress == address)
            if not match:
                continue
            # save it for deletion
            delrlist.append(rkey)
            delnlist.extend(self.routers[rkey].networks)
        if DEBUG:
            _logger.debug('    - delrlist: %r', delrlist)
            _logger.debug('    - delnlist: %r', delnlist)
        # delete the entries
        for rkey in delrlist:
            try:
                del self.routers[rkey]
            except KeyError:
                if DEBUG: _logger.debug('    - rkey not in self.routers: %r', rkey)
        for nkey in delnlist:
            try:
                del self.networks[nkey]
            except KeyError:
                if DEBUG: _logger.debug('    - nkey not in self.networks: %r', rkey)

    def indication(self, pdu):
        if DEBUG: _logger.debug('indication %r', pdu)
        # make sure our configuration is OK
        if not self.adapters:
            raise ConfigurationError('no adapters')
        # might be able to relax this restriction
        if (len(self.adapters) > 1) and (not self.localAdapter):
            raise ConfigurationError('local adapter must be set')
        # get the local adapter
        adapter = self.localAdapter or self.adapters[0]
        # build a generic APDU
        apdu = _APDU(user_data=pdu.pduUserData)
        pdu.encode(apdu)
        if DEBUG: _logger.debug('    - apdu: %r', apdu)
        # build an NPDU specific to where it is going
        npdu = NPDU(user_data=pdu.pduUserData)
        apdu.encode(npdu)
        if DEBUG: _logger.debug('    - npdu: %r', npdu)
        # the hop count always starts out big
        npdu.npduHopCount = 255
        # local stations given to local adapter
        if npdu.pduDestination.addrType == Address.localStationAddr:
            adapter.process_npdu(npdu)
            return
        # local broadcast given to local adapter
        if npdu.pduDestination.addrType == Address.localBroadcastAddr:
            adapter.process_npdu(npdu)
            return
        # global broadcast
        if npdu.pduDestination.addrType == Address.globalBroadcastAddr:
            # set the destination
            npdu.pduDestination = LocalBroadcast()
            npdu.npduDADR = apdu.pduDestination
            # send it to all of connected adapters
            for xadapter in self.adapters:
                xadapter.process_npdu(npdu)
            return
        # remote broadcast
        if (npdu.pduDestination.addrType != Address.remoteBroadcastAddr) and (npdu.pduDestination.addrType != Address.remoteStationAddr):
            raise RuntimeError('invalid destination address type: %s' % (npdu.pduDestination.addrType,))
        dnet = npdu.pduDestination.addrNet
        # if the network matches the local adapter it's local
        if dnet == adapter.adapterNet:
            ### log this, the application shouldn't be sending to a remote station address
            ### when it's a directly connected network
            raise RuntimeError('addressing problem')
        # check for an available path
        if dnet in self.networks:
            rref = self.networks[dnet]
            adapter = rref.adapter
            ### make sure the direct connect is OK, may need to connect
            ### make sure the peer router is OK, may need to connect
            # fix the destination
            npdu.pduDestination = rref.address
            npdu.npduDADR = apdu.pduDestination
            # send it along
            adapter.process_npdu(npdu)
            return
        if DEBUG: _logger.debug('    - no known path to network, broadcast to discover it')
        # set the destination
        npdu.pduDestination = LocalBroadcast()
        npdu.npduDADR = apdu.pduDestination
        # send it to all of the connected adapters
        for xadapter in self.adapters:
            xadapter.process_npdu(npdu)

    def process_npdu(self, adapter, npdu):
        if DEBUG: _logger.debug('process_npdu %r %r', adapter, npdu)
        # make sure our configuration is OK
        if not self.adapters:
            raise ConfigurationError('no adapters')
        if (len(self.adapters) > 1) and (not self.localAdapter):
            raise ConfigurationError('local adapter must be set')
        # check for source routing
        if npdu.npduSADR and (npdu.npduSADR.addrType != Address.nullAddr):
            # see if this is attempting to spoof a directly connected network
            snet = npdu.npduSADR.addrNet
            for xadapter in self.adapters:
                if (xadapter is not adapter) and (snet == xadapter.adapterNet):
                    _logger.warning("spoof?")
                    ### log this
                    return
            # make a key for the router reference
            rkey = (adapter, npdu.pduSource)
            # see if this is spoofing an existing routing table entry
            if snet in self.networks:
                rref = self.networks[snet]
                if rref.adapter == adapter and rref.address == npdu.pduSource:
                    pass        # matches current entry
                else:
                    if DEBUG: _logger.debug('    - replaces entry')
                    ### check to see if this source could be a router to the new network
                    # remove the network from the rref
                    i = rref.networks.index(snet)
                    del rref.networks[i]
                    # remove the network
                    del self.networks[snet]
            # get the router reference for this router
            rref = self.routers.get(rkey)
            if rref:
                if snet not in rref.networks:
                    # add the network
                    rref.networks.append(snet)
                    # reference the snet
                    self.networks[snet] = rref
            else:
                # new reference
                rref = RouterReference( adapter, npdu.pduSource, [snet], 0)
                self.routers[rkey] = rref
                # reference the snet
                self.networks[snet] = rref
        # check for destination routing
        if (not npdu.npduDADR) or (npdu.npduDADR.addrType == Address.nullAddr):
            processLocally = (not self.localAdapter) or (adapter is self.localAdapter) or (npdu.npduNetMessage is not None)
            forwardMessage = False
        elif npdu.npduDADR.addrType == Address.remoteBroadcastAddr:
            if not self.localAdapter:
                return
            if npdu.npduDADR.addrNet == adapter.adapterNet:
                ### log this, attempt to route to a network the device is already on
                return
            processLocally = (npdu.npduDADR.addrNet == self.localAdapter.adapterNet)
            forwardMessage = True
        elif npdu.npduDADR.addrType == Address.remoteStationAddr:
            if not self.localAdapter:
                return
            if npdu.npduDADR.addrNet == adapter.adapterNet:
                ### log this, attempt to route to a network the device is already on
                return
            processLocally = (npdu.npduDADR.addrNet == self.localAdapter.adapterNet) \
                and (npdu.npduDADR.addrAddr == self.localAddress.addrAddr)
            forwardMessage = not processLocally
        elif npdu.npduDADR.addrType == Address.globalBroadcastAddr:
            processLocally = True
            forwardMessage = True
        else:
            _logger.warning('invalid destination address type: %s', npdu.npduDADR.addrType)
            return

        if DEBUG:
            _logger.debug('    - processLocally: %r', processLocally)
            _logger.debug('    - forwardMessage: %r', forwardMessage)
        # application or network layer message
        if npdu.npduNetMessage is None:
            if processLocally and self.serverPeer:
                # decode as a generic APDU
                apdu = _APDU(user_data=npdu.pduUserData)
                apdu.decode(_copy(npdu))
                if DEBUG: _logger.debug('    - apdu: %r', apdu)
                # see if it needs to look routed
                if (len(self.adapters) > 1) and (adapter != self.localAdapter):
                    # combine the source address
                    if not npdu.npduSADR:
                        apdu.pduSource = RemoteStation( adapter.adapterNet, npdu.pduSource.addrAddr )
                    else:
                        apdu.pduSource = npdu.npduSADR
                    # map the destination
                    if not npdu.npduDADR:
                        apdu.pduDestination = self.localAddress
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
                    _logger.debug('    - apdu.pduSource: %r', apdu.pduSource)
                    _logger.debug('    - apdu.pduDestination: %r', apdu.pduDestination)
                # pass upstream to the application layer
                self.response(apdu)
            if not forwardMessage:
                return
        else:
            if processLocally:
                if npdu.npduNetMessage not in npdu_types:
                    if DEBUG: _logger.debug('    - unknown npdu type: %r', npdu.npduNetMessage)
                    return
                # do a deeper decode of the NPDU
                xpdu = npdu_types[npdu.npduNetMessage](user_data=npdu.pduUserData)
                xpdu.decode(_copy(npdu))
                # pass to the service element
                self.sap_request(adapter, xpdu)
            if not forwardMessage:
                return
        # make sure we're really a router
        if len(self.adapters) == 1:
            return
        # make sure it hasn't looped
        if npdu.npduHopCount == 0:
            return
        # build a new NPDU to send to other adapters
        newpdu = _copy(npdu)
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
            newpdu.pduDestination = LocalBroadcast()
            for xadapter in self.adapters:
                if (xadapter is not adapter):
                    xadapter.process_npdu(newpdu)
            return
        if (npdu.npduDADR.addrType == Address.remoteBroadcastAddr) \
                or (npdu.npduDADR.addrType == Address.remoteStationAddr):
            dnet = npdu.npduDADR.addrNet
            # see if this should go to one of our directly connected adapters
            for xadapter in self.adapters:
                if dnet == xadapter.adapterNet:
                    if DEBUG: _logger.debug('    - found direct connect via %r', xadapter)
                    if npdu.npduDADR.addrType == Address.remoteBroadcastAddr:
                        newpdu.pduDestination = LocalBroadcast()
                    else:
                        newpdu.pduDestination = LocalStation(npdu.npduDADR.addrAddr)
                    # last leg in routing
                    newpdu.npduDADR = None
                    # send the packet downstream
                    xadapter.process_npdu(newpdu)
                    return
            # see if we know how to get there
            if dnet in self.networks:
                rref = self.networks[dnet]
                newpdu.pduDestination = rref.address
                ### check to make sure the router is OK
                ### check to make sure the network is OK, may need to connect
                if DEBUG: _logger.debug('    - newpdu: %r', newpdu)
                # send the packet downstream
                rref.adapter.process_npdu(newpdu)
                return
            ### queue this message for reprocessing when the response comes back
            # try to find a path to the network
            xnpdu = WhoIsRouterToNetwork(dnet)
            xnpdu.pduDestination = LocalBroadcast()
            # send it to all of the connected adapters
            for xadapter in self.adapters:
                # skip the horse it rode in on
                if xadapter is adapter:
                    continue
                ### make sure the adapter is OK
                self.sap_indication(xadapter, xnpdu)
        ### log this, what to do?
        return

    def sap_indication(self, adapter, npdu):
        if DEBUG: _logger.debug('sap_indication %r %r', adapter, npdu)
        # encode it as a generic NPDU
        xpdu = NPDU(user_data=npdu.pduUserData)
        npdu.encode(xpdu)
        npdu._xpdu = xpdu
        # tell the adapter to process the NPDU
        adapter.process_npdu(xpdu)

    def sap_confirmation(self, adapter, npdu):
        if DEBUG: _logger.debug('sap_confirmation %r %r', adapter, npdu)
        # encode it as a generic NPDU
        xpdu = NPDU(user_data=npdu.pduUserData)
        npdu.encode(xpdu)
        npdu._xpdu = xpdu
        # tell the adapter to process the NPDU
        adapter.process_npdu(xpdu)
