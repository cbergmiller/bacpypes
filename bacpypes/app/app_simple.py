
import logging
from ..comm import bind
from ..link import Address

from ..network import NetworkServiceAccessPoint, NetworkServiceElement
from ..bvll import BIPSimple, AnnexJCodec, UDPMultiplexer
from .state_machine_ap import StateMachineAccessPoint
from .app_service_ap import ApplicationServiceAccessPoint
from .app_io_controller import ApplicationIOController
# basic services
from ..service.device import WhoIsIAmServices
from ..service.object import ReadWritePropertyServices

_logger = logging.getLogger(__name__)
__all__ = ['BIPSimpleApplication']


class BIPSimpleApplication(ApplicationIOController, WhoIsIAmServices, ReadWritePropertyServices):
    """
    BIPSimpleApplication
    """
    def __init__(self, local_device, local_address, deviceInfoCache=None, aseID=None):
        ApplicationIOController.__init__(self, local_device, local_address, deviceInfoCache, aseID=aseID)
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
        self.bip = BIPSimple()
        self.annexj = AnnexJCodec()
        self.mux = UDPMultiplexer(self.localAddress)
        # bind the bottom layers
        bind(self.bip, self.annexj, self.mux.annexJ)
        # bind the BIP stack to the network, no network number
        self.nsap.bind(self.bip)

    async def create_endoint(self):
        await self.mux.create_endpoint()

    def close_socket(self):
        # pass to the multiplexer, then down to the sockets
        self.mux.close_endpoint()
