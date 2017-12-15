
import logging
from ..comm import Client, Server
from ..link import PDU
from .bvlpdu import BVLPDU, bvl_pdu_types

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['AnnexJCodec']


class AnnexJCodec(Client, Server):

    def __init__(self, cid=None, sid=None):
        if DEBUG: _logger.debug("__init__ cid=%r sid=%r", cid, sid)
        Client.__init__(self, cid)
        Server.__init__(self, sid)

    def indication(self, rpdu):
        if DEBUG: _logger.debug("indication %r", rpdu)
        # encode it as a generic BVLL PDU
        bvlpdu = BVLPDU()
        rpdu.encode(bvlpdu)
        # encode it as a PDU
        pdu = PDU()
        bvlpdu.encode(pdu)
        # send it downstream
        self.request(pdu)

    def confirmation(self, pdu):
        if DEBUG: _logger.debug("confirmation %r", pdu)
        # interpret as a BVLL PDU
        bvlpdu = BVLPDU()
        bvlpdu.decode(pdu)
        # get the class related to the function
        rpdu = bvl_pdu_types[bvlpdu.bvlciFunction]()
        rpdu.decode(bvlpdu)
        # send it upstream
        self.response(rpdu)
