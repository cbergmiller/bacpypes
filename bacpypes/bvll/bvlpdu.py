import logging
from ..debugging import DebugContents
from ..comm import PDUData
from ..link import Address, unpack_ip_addr
from .bvlci import BVLCI

_logger = logging.getLogger(__name__)
__all__ = [
    'BVLPDU', 'bvl_pdu_types', 'Result', 'WriteBroadcastDistributionTable', 'ReadBroadcastDistributionTable',
    'ReadBroadcastDistributionTableAck', 'ForwardedNPDU', 'FDTEntry', 'RegisterForeignDevice', 'ReadForeignDeviceTable',
    'ReadForeignDeviceTableAck', 'DeleteForeignDeviceTableEntry', 'DistributeBroadcastToNetwork', 'OriginalUnicastNPDU',
    'OriginalBroadcastNPDU'
]

# a dictionary of message type values and classes
bvl_pdu_types = {}


def register_bvlpdu_type(cls):
    bvl_pdu_types[cls.messageType] = cls


def key_value_contents(use_dict=None, as_class=dict, key_values=()):
    """Return the contents of an object as a dict."""
    _logger.debug('key_value_contents use_dict=%r as_class=%r key_values=%r', use_dict, as_class, key_values)
    # make/extend the dictionary of content
    if use_dict is None:
        use_dict = as_class()
    # loop through the values and save them
    for k, v in key_values:
        if v is not None:
            if hasattr(v, 'dict_contents'):
                v = v.dict_contents(as_class=as_class)
            use_dict.__setitem__(k, v)
    # return what we built/updated
    return use_dict


class BVLPDU(BVLCI, PDUData):
    """
    BACnet Virtual Link Layer Module
    """

    def __init__(self, *args, **kwargs):
        _logger.debug('__init__ %r %r', args, kwargs)
        super(BVLPDU, self).__init__(*args, **kwargs)

    def encode(self, pdu):
        BVLCI.encode(self, pdu)
        pdu.put_data(self.pduData)

    def decode(self, pdu):
        BVLCI.decode(self, pdu)
        self.pduData = pdu.get_data(len(pdu.pduData))

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        return PDUData.pdudata_contents(self, use_dict=use_dict, as_class=as_class)

    def dict_contents(self, use_dict=None, as_class=dict, key_values=()):
        """Return the contents of an object as a dict."""
        _logger.debug('dict_contents use_dict=%r as_class=%r key_values=%r', use_dict, as_class, key_values)
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # call the superclasses
        self.bvlci_contents(use_dict=use_dict, as_class=as_class)
        self.bvlpdu_contents(use_dict=use_dict, as_class=as_class)
        # return what we built/updated
        return use_dict


class Result(BVLPDU):
    _debug_contents = ('bvlciResultCode',)
    messageType = BVLCI.result

    def __init__(self, code=None, *args, **kwargs):
        super(Result, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.result
        self.bvlciLength = 6
        self.bvlciResultCode = code

    def encode(self, bvlpdu):
        BVLCI.update(bvlpdu, self)
        bvlpdu.put_short(self.bvlciResultCode)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)
        self.bvlciResultCode = bvlpdu.get_short()

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'Result'),
                ('result_code', self.bvlciResultCode),
            )
        )


register_bvlpdu_type(Result)


class WriteBroadcastDistributionTable(BVLPDU):
    _debug_contents = ('bvlciBDT',)

    messageType = BVLCI.writeBroadcastDistributionTable

    def __init__(self, bdt=[], *args, **kwargs):
        super(WriteBroadcastDistributionTable, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.writeBroadcastDistributionTable
        self.bvlciLength = 4 + 10 * len(bdt)
        self.bvlciBDT = bdt

    def encode(self, bvlpdu):
        BVLCI.update(bvlpdu, self)
        for bdte in self.bvlciBDT:
            bvlpdu.put_data(bdte.addrAddr)
            bvlpdu.put_long(bdte.addrMask)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)
        self.bvlciBDT = []
        while bvlpdu.pduData:
            bdte = Address(unpack_ip_addr(bvlpdu.get_data(6)))
            bdte.addrMask = bvlpdu.get_long()
            self.bvlciBDT.append(bdte)

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        broadcast_distribution_table = []
        for bdte in self.bvlciBDT:
            broadcast_distribution_table.append(str(bdte))
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'WriteBroadcastDistributionTable'),
                ('bdt', broadcast_distribution_table),
            )
        )


register_bvlpdu_type(WriteBroadcastDistributionTable)


class ReadBroadcastDistributionTable(BVLPDU):
    messageType = BVLCI.readBroadcastDistributionTable

    def __init__(self, *args, **kwargs):
        super(ReadBroadcastDistributionTable, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.readBroadcastDistributionTable
        self.bvlciLength = 4

    def encode(self, bvlpdu):
        BVLCI.update(bvlpdu, self)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(('function', 'ReadBroadcastDistributionTable'),)
        )


register_bvlpdu_type(ReadBroadcastDistributionTable)


class ReadBroadcastDistributionTableAck(BVLPDU):
    _debug_contents = ('bvlciBDT',)

    messageType = BVLCI.readBroadcastDistributionTableAck

    def __init__(self, bdt=[], *args, **kwargs):
        super(ReadBroadcastDistributionTableAck, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.readBroadcastDistributionTableAck
        self.bvlciLength = 4 + 10 * len(bdt)
        self.bvlciBDT = bdt

    def encode(self, bvlpdu):
        # make sure the length is correct
        self.bvlciLength = 4 + 10 * len(self.bvlciBDT)
        BVLCI.update(bvlpdu, self)
        # encode the table
        for bdte in self.bvlciBDT:
            bvlpdu.put_data(bdte.addrAddr)
            bvlpdu.put_long(bdte.addrMask)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)

        # decode the table
        self.bvlciBDT = []
        while bvlpdu.pduData:
            bdte = Address(unpack_ip_addr(bvlpdu.get_data(6)))
            bdte.addrMask = bvlpdu.get_long()
            self.bvlciBDT.append(bdte)

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        broadcast_distribution_table = []
        for bdte in self.bvlciBDT:
            broadcast_distribution_table.append(str(bdte))
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'ReadBroadcastDistributionTableAck'),
                ('bdt', broadcast_distribution_table),
            )
        )


register_bvlpdu_type(ReadBroadcastDistributionTableAck)


class ForwardedNPDU(BVLPDU):
    _debug_contents = ('bvlciAddress',)

    messageType = BVLCI.forwardedNPDU

    def __init__(self, addr=None, *args, **kwargs):
        super(ForwardedNPDU, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.forwardedNPDU
        self.bvlciLength = 10 + len(self.pduData)
        self.bvlciAddress = addr

    def encode(self, bvlpdu):
        # make sure the length is correct
        self.bvlciLength = 10 + len(self.pduData)
        BVLCI.update(bvlpdu, self)
        # encode the address
        bvlpdu.put_data(self.bvlciAddress.addrAddr)
        # encode the rest of the data
        bvlpdu.put_data(self.pduData)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)
        # get the address
        self.bvlciAddress = Address(unpack_ip_addr(bvlpdu.get_data(6)))
        # get the rest of the data
        self.pduData = bvlpdu.get_data(len(bvlpdu.pduData))

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'ForwardedNPDU'),
                ('address', str(self.bvlciAddress)),
            )
        )
        # this message has data
        PDUData.dict_contents(self, use_dict=use_dict, as_class=as_class)
        # return what we built/updated
        return use_dict


register_bvlpdu_type(ForwardedNPDU)


class FDTEntry(DebugContents):
    _debug_contents = ('fdAddress', 'fdTTL', 'fdRemain')

    def __init__(self):
        self.fdAddress = None
        self.fdTTL = None
        self.fdRemain = None

    def __eq__(self, other):
        """Return true iff entries are identical."""
        return (self.fdAddress == other.fdAddress) and \
               (self.fdTTL == other.fdTTL) and (self.fdRemain == other.fdRemain)

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # save the content
        use_dict.__setitem__('address', str(self.fdAddress))
        use_dict.__setitem__('ttl', self.fdTTL)
        use_dict.__setitem__('remaining', self.fdRemain)
        # return what we built/updated
        return use_dict


class RegisterForeignDevice(BVLPDU):
    _debug_contents = ('bvlciTimeToLive',)

    messageType = BVLCI.registerForeignDevice

    def __init__(self, ttl=None, *args, **kwargs):
        super(RegisterForeignDevice, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.registerForeignDevice
        self.bvlciLength = 6
        self.bvlciTimeToLive = ttl

    def encode(self, bvlpdu):
        BVLCI.update(bvlpdu, self)
        bvlpdu.put_short(self.bvlciTimeToLive)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)
        self.bvlciTimeToLive = bvlpdu.get_short()

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'RegisterForeignDevice'),
                ('ttl', self.bvlciTimeToLive),
            )
        )


register_bvlpdu_type(RegisterForeignDevice)


class ReadForeignDeviceTable(BVLPDU):
    messageType = BVLCI.readForeignDeviceTable

    def __init__(self, ttl=None, *args, **kwargs):
        super(ReadForeignDeviceTable, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.readForeignDeviceTable
        self.bvlciLength = 4

    def encode(self, bvlpdu):
        BVLCI.update(bvlpdu, self)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'ReadForeignDeviceTable'),
            )
        )


register_bvlpdu_type(ReadForeignDeviceTable)


class ReadForeignDeviceTableAck(BVLPDU):
    _debug_contents = ('bvlciFDT',)

    messageType = BVLCI.readForeignDeviceTableAck

    def __init__(self, fdt=[], *args, **kwargs):
        super(ReadForeignDeviceTableAck, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.readForeignDeviceTableAck
        self.bvlciLength = 4 + 10 * len(fdt)
        self.bvlciFDT = fdt

    def encode(self, bvlpdu):
        BVLCI.update(bvlpdu, self)
        for fdte in self.bvlciFDT:
            bvlpdu.put_data(fdte.fdAddress.addrAddr)
            bvlpdu.put_short(fdte.fdTTL)
            bvlpdu.put_short(fdte.fdRemain)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)
        self.bvlciFDT = []
        while bvlpdu.pduData:
            fdte = FDTEntry()
            fdte.fdAddress = Address(unpack_ip_addr(bvlpdu.get_data(6)))
            fdte.fdTTL = bvlpdu.get_short()
            fdte.fdRemain = bvlpdu.get_short()
            self.bvlciFDT.append(fdte)

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        foreign_device_table = []
        for fdte in self.bvlciFDT:
            foreign_device_table.append(fdte.dict_contents(as_class=as_class))
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'ReadForeignDeviceTableAck'),
                ('foreign_device_table', foreign_device_table),
            )
        )


register_bvlpdu_type(ReadForeignDeviceTableAck)


class DeleteForeignDeviceTableEntry(BVLPDU):
    _debug_contents = ('bvlciAddress',)

    messageType = BVLCI.deleteForeignDeviceTableEntry

    def __init__(self, addr=None, *args, **kwargs):
        super(DeleteForeignDeviceTableEntry, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.deleteForeignDeviceTableEntry
        self.bvlciLength = 10
        self.bvlciAddress = addr

    def encode(self, bvlpdu):
        BVLCI.update(bvlpdu, self)
        bvlpdu.put_data(self.bvlciAddress.addrAddr)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)
        self.bvlciAddress = Address(unpack_ip_addr(bvlpdu.get_data(6)))

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'DeleteForeignDeviceTableEntry'),
                ('address', str(self.bvlciAddress)),
            )
        )


register_bvlpdu_type(DeleteForeignDeviceTableEntry)


class DistributeBroadcastToNetwork(BVLPDU):
    messageType = BVLCI.distributeBroadcastToNetwork

    def __init__(self, *args, **kwargs):
        super(DistributeBroadcastToNetwork, self).__init__(*args, **kwargs)

        self.bvlciFunction = BVLCI.distributeBroadcastToNetwork
        self.bvlciLength = 4 + len(self.pduData)

    def encode(self, bvlpdu):
        self.bvlciLength = 4 + len(self.pduData)
        BVLCI.update(bvlpdu, self)
        bvlpdu.put_data(self.pduData)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)
        self.pduData = bvlpdu.get_data(len(bvlpdu.pduData))

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'DistributeBroadcastToNetwork'),
            )
        )
        # this message has data
        PDUData.dict_contents(self, use_dict=use_dict, as_class=as_class)
        # return what we built/updated
        return use_dict


register_bvlpdu_type(DistributeBroadcastToNetwork)


class OriginalUnicastNPDU(BVLPDU):
    messageType = BVLCI.originalUnicastNPDU

    def __init__(self, *args, **kwargs):
        super(OriginalUnicastNPDU, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.originalUnicastNPDU
        self.bvlciLength = 4 + len(self.pduData)

    def encode(self, bvlpdu):
        self.bvlciLength = 4 + len(self.pduData)
        BVLCI.update(bvlpdu, self)
        bvlpdu.put_data(self.pduData)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)
        self.pduData = bvlpdu.get_data(len(bvlpdu.pduData))

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'OriginalUnicastNPDU'),
            )
        )
        # this message has data
        PDUData.dict_contents(self, use_dict=use_dict, as_class=as_class)
        # return what we built/updated
        return use_dict


register_bvlpdu_type(OriginalUnicastNPDU)


class OriginalBroadcastNPDU(BVLPDU):
    messageType = BVLCI.originalBroadcastNPDU

    def __init__(self, *args, **kwargs):
        super(OriginalBroadcastNPDU, self).__init__(*args, **kwargs)
        self.bvlciFunction = BVLCI.originalBroadcastNPDU
        self.bvlciLength = 4 + len(self.pduData)

    def encode(self, bvlpdu):
        self.bvlciLength = 4 + len(self.pduData)
        BVLCI.update(bvlpdu, self)
        bvlpdu.put_data(self.pduData)

    def decode(self, bvlpdu):
        BVLCI.update(self, bvlpdu)
        self.pduData = bvlpdu.get_data(len(bvlpdu.pduData))

    def bvlpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ('function', 'OriginalBroadcastNPDU'),
            )
        )
        # this message has data
        PDUData.dict_contents(self, use_dict=use_dict, as_class=as_class)
        # return what we built/updated
        return use_dict


register_bvlpdu_type(OriginalBroadcastNPDU)
