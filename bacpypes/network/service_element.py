
import logging

from ..comm import ApplicationServiceElement
from ..link import LocalBroadcast, RemoteStation
from .npdu import IAmRouterToNetwork, NPDU, WhoIsRouterToNetwork, npdu_types

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['NetworkServiceElement']


class NetworkServiceElement(ApplicationServiceElement):

    def __init__(self, eid=None):
        if DEBUG: _logger.debug('__init__ eid=%r', eid)
        ApplicationServiceElement.__init__(self, eid)

    def indication(self, adapter, npdu):
        if DEBUG: _logger.debug('indication %r %r', adapter, npdu)
        # redirect
        fn = npdu.__class__.__name__
        if hasattr(self, fn):
            getattr(self, fn)(adapter, npdu)

    def confirmation(self, adapter, npdu):
        if DEBUG: _logger.debug('confirmation %r %r', adapter, npdu)
        # redirect
        fn = npdu.__class__.__name__
        if hasattr(self, fn):
            getattr(self, fn)(adapter, npdu)

    def WhoIsRouterToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug('WhoIsRouterToNetwork %r %r', adapter, npdu)
        # reference the service access point
        sap = self.elementService
        if DEBUG: _logger.debug('    - sap: %r', sap)
        # if we're not a router, skip it
        if len(sap.adapters) == 1:
            if DEBUG: _logger.debug('    - not a router')
            return
        if npdu.wirtnNetwork is None:
            # requesting all networks
            if DEBUG: _logger.debug('    - requesting all networks')
            # build a list of reachable networks
            netlist = []
            # start with directly connected networks
            for xadapter in sap.adapters:
                if xadapter is not adapter:
                    netlist.append(xadapter.adapterNet)
            # build a list of other available networks
            for net, rref in sap.networks.items():
                if rref.adapter is not adapter:
                    ### skip those marked unreachable
                    ### skip those that are not available
                    netlist.append(net)
            if netlist:
                if DEBUG: _logger.debug('    - found these: %r', netlist)
                # build a response
                iamrtn = IAmRouterToNetwork(netlist, user_data=npdu.pduUserData)
                iamrtn.pduDestination = npdu.pduSource
                # send it back
                self.response(adapter, iamrtn)
        else:
            # requesting a specific network
            if DEBUG: _logger.debug('    - requesting specific network: %r', npdu.wirtnNetwork)
            # start with directly connected networks
            for xadapter in sap.adapters:
                if (xadapter is not adapter) and (npdu.wirtnNetwork == xadapter.adapterNet):
                    if DEBUG: _logger.debug('    - found it directly connected')
                    # build a response
                    iamrtn = IAmRouterToNetwork([npdu.wirtnNetwork], user_data=npdu.pduUserData)
                    iamrtn.pduDestination = npdu.pduSource
                    # send it back
                    self.response(adapter, iamrtn)
                    break
            else:
                # check for networks I know about
                if npdu.wirtnNetwork in sap.networks:
                    rref = sap.networks[npdu.wirtnNetwork]
                    if rref.adapter is adapter:
                        if DEBUG: _logger.debug('    - same net as request')
                    else:
                        if DEBUG: _logger.debug('    - found on adapter: %r', rref.adapter)
                        # build a response
                        iamrtn = IAmRouterToNetwork([npdu.wirtnNetwork], user_data=npdu.pduUserData)
                        iamrtn.pduDestination = npdu.pduSource
                        # send it back
                        self.response(adapter, iamrtn)
                else:
                    if DEBUG: _logger.debug('    - forwarding request to other adapters')
                    # build a request
                    whoisrtn = WhoIsRouterToNetwork(npdu.wirtnNetwork, user_data=npdu.pduUserData)
                    whoisrtn.pduDestination = LocalBroadcast()
                    # if the request had a source, forward it along
                    if npdu.npduSADR:
                        whoisrtn.npduSADR = npdu.npduSADR
                    else:
                        whoisrtn.npduSADR = RemoteStation(adapter.adapterNet, npdu.pduSource.addrAddr)
                    if DEBUG: _logger.debug('    - whoisrtn: %r', whoisrtn)
                    # send it to all of the (other) adapters
                    for xadapter in sap.adapters:
                        if xadapter is not adapter:
                            if DEBUG: _logger.debug('    - sending on adapter: %r', xadapter)
                            self.request(xadapter, whoisrtn)

    def IAmRouterToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug('IAmRouterToNetwork %r %r', adapter, npdu)
        # pass along to the service access point
        self.elementService.add_router_references(adapter, npdu.pduSource, npdu.iartnNetworkList)

    def ICouldBeRouterToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug('ICouldBeRouterToNetwork %r %r', adapter, npdu)
        # reference the service access point
        # sap = self.elementService

    def RejectMessageToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug('RejectMessageToNetwork %r %r', adapter, npdu)
        # reference the service access point
        # sap = self.elementService

    def RouterBusyToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug('RouterBusyToNetwork %r %r', adapter, npdu)
        # reference the service access point
        # sap = self.elementService

    def RouterAvailableToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug('RouterAvailableToNetwork %r %r', adapter, npdu)
        # reference the service access point
        # sap = self.elementService

    def InitializeRoutingTable(self, adapter, npdu):
        if DEBUG: _logger.debug('InitializeRoutingTable %r %r', adapter, npdu)
        # reference the service access point
        # sap = self.elementService

    def InitializeRoutingTableAck(self, adapter, npdu):
        if DEBUG: _logger.debug('InitializeRoutingTableAck %r %r', adapter, npdu)
        # reference the service access point
        # sap = self.elementService

    def EstablishConnectionToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug('EstablishConnectionToNetwork %r %r', adapter, npdu)
        # reference the service access point
        # sap = self.elementService

    def DisconnectConnectionToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug('DisconnectConnectionToNetwork %r %r', adapter, npdu)
        # reference the service access point
        # sap = self.elementService

