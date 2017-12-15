
import logging
from ..comm import bind
from ..link import Address

from ..network import NetworkServiceAccessPoint, NetworkServiceElement
from ..bvll import BIPSimple, AnnexJCodec, UDPMultiplexer

_logger = logging.getLogger(__name__)
__all__ = ['BIPNetworkApplication']


class BIPNetworkApplication(NetworkServiceElement):
    """
    BIPNetworkApplication
    """
    def __init__(self, local_address, eID=None):
        NetworkServiceElement.__init__(self, eID)
        # allow the address to be cast to the correct type
        if isinstance(local_address, Address):
            self.localAddress = local_address
        else:
            self.localAddress = Address(local_address)
        # a network service access point will be needed
        self.nsap = NetworkServiceAccessPoint()
        # give the NSAP a generic network layer service element
        bind(self, self.nsap)
        # create a generic BIP stack, bound to the Annex J server
        # on the UDP multiplexer
        self.bip = BIPSimple()
        self.annexj = AnnexJCodec()
        self.mux = UDPMultiplexer(self.localAddress)
        # bind the bottom layers
        bind(self.bip, self.annexj, self.mux.annexJ)
        # bind the NSAP to the stack, no network number
        self.nsap.bind(self.bip)
