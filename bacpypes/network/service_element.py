
import logging

from ..comm import ApplicationServiceElement
from ..link import LocalBroadcast, RemoteStation
from .npdu import IAmRouterToNetwork, NPDU, WhoIsRouterToNetwork, npdu_types

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['NetworkServiceElement']


class NetworkServiceElement(ApplicationServiceElement):

    def __init__(self, eid=None):
        if DEBUG: _logger.debug("__init__ eid=%r", eid)
        ApplicationServiceElement.__init__(self, eid)

    def indication(self, adapter, npdu):
        if DEBUG: _logger.debug("indication %r %r", adapter, npdu)

        # redirect
        fn = npdu.__class__.__name__
        if hasattr(self, fn):
            getattr(self, fn)(adapter, npdu)

    def confirmation(self, adapter, npdu):
        if DEBUG: _logger.debug("confirmation %r %r", adapter, npdu)

        # redirect
        fn = npdu.__class__.__name__
        if hasattr(self, fn):
            getattr(self, fn)(adapter, npdu)

    #-----

    def WhoIsRouterToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug("WhoIsRouterToNetwork %r %r", adapter, npdu)

        # reference the service access point
        sap = self.elementService
        if DEBUG: _logger.debug("    - sap: %r", sap)

        # if we're not a router, skip it
        if len(sap.adapters) == 1:
            if DEBUG: _logger.debug("    - not a router")
            return

        if npdu.wirtnNetwork is None:
            # requesting all networks
            if DEBUG: _logger.debug("    - requesting all networks")

            # build a list of reachable networks
            netlist = []

            # loop through the adapters
            for xadapter in sap.adapters.values():
                if (xadapter is adapter):
                    continue

                # add the direct network
                netlist.append(xadapter.adapterNet)

                ### add the other reachable

            if netlist:
                if DEBUG: _logger.debug("    - found these: %r", netlist)

                # build a response
                iamrtn = IAmRouterToNetwork(netlist, user_data=npdu.pduUserData)
                iamrtn.pduDestination = npdu.pduSource

                # send it back
                self.response(adapter, iamrtn)

        else:
            # requesting a specific network
            if DEBUG: _logger.debug("    - requesting specific network: %r", npdu.wirtnNetwork)
            dnet = npdu.wirtnNetwork

            # check the directly connected networks
            if dnet in sap.adapters:
                if DEBUG: _logger.debug("    - directly connected")

                # build a response
                iamrtn = IAmRouterToNetwork([dnet], user_data=npdu.pduUserData)
                iamrtn.pduDestination = npdu.pduSource

                # send it back
                self.response(adapter, iamrtn)

            else:
                # see if there is routing information for this source network
                router_info = sap.router_info_cache.get_router_info(dnet)
                if router_info:
                    if DEBUG: _logger.debug("    - router found")

                    router_net, router_address, router_status = router_info
                    if DEBUG: _logger.debug(
                        "    - router_net, router_address, router_status: %r, %r, %r",
                        router_net, router_address, router_status,
                        )
                    if router_net not in sap.adapters:
                        if DEBUG: _logger.debug("    - path error (6)")
                        return

                    # build a response
                    iamrtn = IAmRouterToNetwork([dnet], user_data=npdu.pduUserData)
                    iamrtn.pduDestination = npdu.pduSource

                    # send it back
                    self.response(adapter, iamrtn)

                else:
                    if DEBUG: _logger.debug("    - forwarding request to other adapters")

                    # build a request
                    whoisrtn = WhoIsRouterToNetwork(dnet, user_data=npdu.pduUserData)
                    whoisrtn.pduDestination = LocalBroadcast()

                    # if the request had a source, forward it along
                    if npdu.npduSADR:
                        whoisrtn.npduSADR = npdu.npduSADR
                    else:
                        whoisrtn.npduSADR = RemoteStation(adapter.adapterNet, npdu.pduSource.addrAddr)
                    if DEBUG: _logger.debug("    - whoisrtn: %r", whoisrtn)

                    # send it to all of the (other) adapters
                    for xadapter in sap.adapters.values():
                        if xadapter is not adapter:
                            if DEBUG: _logger.debug("    - sending on adapter: %r", xadapter)
                            self.request(xadapter, whoisrtn)

    def IAmRouterToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug("IAmRouterToNetwork %r %r", adapter, npdu)

        # reference the service access point
        sap = self.elementService
        if DEBUG: _logger.debug("    - sap: %r", sap)

        # pass along to the service access point
        sap.add_router_references(adapter.adapterNet, npdu.pduSource, npdu.iartnNetworkList)

        # skip if this is not a router
        if len(sap.adapters) > 1:
            # build a broadcast annoucement
            iamrtn = IAmRouterToNetwork(npdu.iartnNetworkList, user_data=npdu.pduUserData)
            iamrtn.pduDestination = LocalBroadcast()

            # send it to all of the connected adapters
            for xadapter in sap.adapters.values():
                # skip the horse it rode in on
                if (xadapter is adapter):
                    continue

                # request this
                self.request(xadapter, iamrtn)

        # look for pending NPDUs for the networks
        for dnet in npdu.iartnNetworkList:
            pending_npdus = sap.pending_nets.get(dnet, None)
            if pending_npdus is not None:
                if DEBUG: _logger.debug("    - %d pending to %r", len(pending_npdus), dnet)

                # delete the references
                del sap.pending_nets[dnet]

                # now reprocess them
                for pending_npdu in pending_npdus:
                    if DEBUG: _logger.debug("    - sending %s", repr(pending_npdu))

                    # the destination is the address of the router
                    pending_npdu.pduDestination = npdu.pduSource

                    # send the packet downstream
                    adapter.process_npdu(pending_npdu)

    def ICouldBeRouterToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug("ICouldBeRouterToNetwork %r %r", adapter, npdu)

        # reference the service access point
        # sap = self.elementService

    def RejectMessageToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug("RejectMessageToNetwork %r %r", adapter, npdu)

        # reference the service access point
        # sap = self.elementService

    def RouterBusyToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug("RouterBusyToNetwork %r %r", adapter, npdu)

        # reference the service access point
        # sap = self.elementService

    def RouterAvailableToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug("RouterAvailableToNetwork %r %r", adapter, npdu)

        # reference the service access point
        # sap = self.elementService

    def InitializeRoutingTable(self, adapter, npdu):
        if DEBUG: _logger.debug("InitializeRoutingTable %r %r", adapter, npdu)

        # reference the service access point
        # sap = self.elementService

    def InitializeRoutingTableAck(self, adapter, npdu):
        if DEBUG: _logger.debug("InitializeRoutingTableAck %r %r", adapter, npdu)

        # reference the service access point
        # sap = self.elementService

    def EstablishConnectionToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug("EstablishConnectionToNetwork %r %r", adapter, npdu)

        # reference the service access point
        # sap = self.elementService

    def DisconnectConnectionToNetwork(self, adapter, npdu):
        if DEBUG: _logger.debug("DisconnectConnectionToNetwork %r %r", adapter, npdu)

        # reference the service access point
        # sap = self.elementService
