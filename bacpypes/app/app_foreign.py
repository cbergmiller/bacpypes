
import logging
from ..comm import bind
from ..link import Address

from ..network import NetworkServiceAccessPoint, NetworkServiceElement
from ..bvll import BIPForeign, AnnexJCodec, UDPMultiplexer
from .state_machine_ap import StateMachineAccessPoint
from .app_service_ap import ApplicationServiceAccessPoint
from .app_io_controller import ApplicationIOController
# basic services
from ..service.device import WhoIsIAmServices
from ..service.object import ReadWritePropertyServices

_logger = logging.getLogger(__name__)
__all__ = ['BIPForeignApplication']


class BIPForeignApplication(ApplicationIOController, WhoIsIAmServices, ReadWritePropertyServices):
    """
    BIPForeignApplication
    """
    def __init__(self, local_device, local_address, bbmd_address, bbmd_ttl, deviceInfoCache=None, aseID=None):
        ApplicationIOController.__init__(self, local_device, deviceInfoCache, aseID=aseID)
        # local address might be useful for subclasses
        if isinstance(local_address, Address):
            self.localAddress = local_address
        else:
            self.localAddress = Address(local_address)
        # include a application decoder
        self.asap = ApplicationServiceAccessPoint()
        # pass the device object to the state machine access point so it
        # can know if it should support segmentation
        self.smap = StateMachineAccessPoint(local_device)
        # the segmentation state machines need access to the same device
        # information cache as the application
        self.smap.deviceInfoCache = self.deviceInfoCache
        # a network service access point will be needed
        self.nsap = NetworkServiceAccessPoint()
        # give the NSAP a generic network layer service element
        self.nse = NetworkServiceElement()
        bind(self.nse, self.nsap)
        # bind the top layers
        bind(self, self.asap, self.smap, self.nsap)
        # create a generic BIP stack, bound to the Annex J server
        # on the UDP multiplexer
        self.bip = BIPForeign(bbmd_address, bbmd_ttl)
        self.annexj = AnnexJCodec()
        self.mux = UDPMultiplexer(self.localAddress, no_broadcast=True)
        # bind the bottom layers
        bind(self.bip, self.annexj, self.mux.annexJ)
        # bind the NSAP to the stack, no network number
        self.nsap.bind(self.bip)

    async def create_endoint(self):
        await self.mux.create_endpoint()

    def close_endpoint(self):
        # pass to the multiplexer, then down to the sockets
        self.mux.close_endpoint()
