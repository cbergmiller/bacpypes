
import pickle
from io import StringIO
from ..comm import PDU
__all__ = ['PickleActorMixIn']


class PickleActorMixIn:

    def __init__(self, *args):
        super(PickleActorMixIn, self).__init__(*args)
        # keep an upstream buffer
        self.pickleBuffer = ''

    def indication(self, pdu):
        # pickle the data
        pdu.pduData = pickle.dumps(pdu.pduData)
        # continue as usual
        super(PickleActorMixIn, self).indication(pdu)

    def response(self, pdu):
        # add the data to our buffer
        self.pickleBuffer += pdu.pduData
        # build a file-like object around the buffer
        strm = StringIO(self.pickleBuffer)
        pos = 0
        while pos < strm.len:
            try:
                # try to load something
                msg = pickle.load(strm)
            except:
                break

            # got a message
            rpdu = PDU(msg)
            rpdu.update(pdu)

            super(PickleActorMixIn, self).response(rpdu)

            # see where we are
            pos = strm.tell()

        # save anything left over, if there is any
        if (pos < strm.len):
            self.pickleBuffer = self.pickleBuffer[pos:]
        else:
            self.pickleBuffer = ''
