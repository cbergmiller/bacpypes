#!/usr/bin/python

import logging
from ..debugging import ModuleLogger, DebugContents, bacpypes_debugging, btox
from .npci import NPCI
from ..comm import PDUData


_logger = logging.getLogger(__name__)
__all__ = ['NPDU', 'WhoIsRouterToNetwork', 'IAmRouterToNetwork', 'ICouldBeRouterToNetwork', 'RejectMessageToNetwork',
           'RouterBusyToNetwork', 'RouterAvailableToNetwork', 'RoutingTableEntry', 'InitializeRoutingTable',
           'InitializeRoutingTableAck', 'EstablishConnectionToNetwork', 'DisconnectConnectionToNetwork',
           'WhatIsNetworkNumber', 'NetworkNumberIs', 'npdu_types']

# a dictionary of message type values and classes
npdu_types = {}

def register_npdu_type(klass):
    npdu_types[klass.messageType] = klass


#
#   NPDU
#

@bacpypes_debugging
class NPDU(NPCI, PDUData):

    def __init__(self, *args, **kwargs):
        super(NPDU, self).__init__(*args, **kwargs)

    def encode(self, pdu):
        NPCI.encode(self, pdu)
        pdu.put_data(self.pduData)

    def decode(self, pdu):
        NPCI.decode(self, pdu)
        self.pduData = pdu.get_data(len(pdu.pduData))

    def npdu_contents(self, use_dict=None, as_class=dict):
        return PDUData.pdudata_contents(self, use_dict=use_dict, as_class=as_class)

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug: NPDU._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # call the parent classes
        self.npci_contents(use_dict=use_dict, as_class=as_class)
        self.npdu_contents(use_dict=use_dict, as_class=as_class)
        # return what we built/updated
        return use_dict

#
#   key_value_contents
#

@bacpypes_debugging
def key_value_contents(use_dict=None, as_class=dict, key_values=()):
    """Return the contents of an object as a dict."""
    if _debug: key_value_contents._debug("key_value_contents use_dict=%r as_class=%r key_values=%r", use_dict, as_class, key_values)
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

#------------------------------

#
#   WhoIsRouterToNetwork
#

class WhoIsRouterToNetwork(NPDU):

    _debug_contents = ('wirtnNetwork',)

    messageType = 0x00

    def __init__(self, net=None, *args, **kwargs):
        super(WhoIsRouterToNetwork, self).__init__(*args, **kwargs)

        self.npduNetMessage = WhoIsRouterToNetwork.messageType
        self.wirtnNetwork = net

    def encode(self, npdu):
        NPCI.update(npdu, self)
        if self.wirtnNetwork is not None:
            npdu.put_short( self.wirtnNetwork )

    def decode(self, npdu):
        NPCI.update(self, npdu)
        if npdu.pduData:
            self.wirtnNetwork = npdu.get_short()
        else:
            self.wirtnNetwork = None

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'WhoIsRouterToNetwork'),
                ('network', self.wirtnNetwork),
            ))

register_npdu_type(WhoIsRouterToNetwork)

#
#   IAmRouterToNetwork
#

class IAmRouterToNetwork(NPDU):

    _debug_contents = ('iartnNetworkList',)

    messageType = 0x01

    def __init__(self, netList=[], *args, **kwargs):
        super(IAmRouterToNetwork, self).__init__(*args, **kwargs)

        self.npduNetMessage = IAmRouterToNetwork.messageType
        self.iartnNetworkList = netList

    def encode(self, npdu):
        NPCI.update(npdu, self)
        for net in self.iartnNetworkList:
            npdu.put_short(net)

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.iartnNetworkList = []
        while npdu.pduData:
            self.iartnNetworkList.append(npdu.get_short())

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'IAmRouterToNetwork'),
                ('network_list', self.iartnNetworkList),
            ))

register_npdu_type(IAmRouterToNetwork)

#
#   ICouldBeRouterToNetwork
#

class ICouldBeRouterToNetwork(NPDU):

    _debug_contents = ('icbrtnNetwork','icbrtnPerformanceIndex')

    messageType = 0x02

    def __init__(self, net=None, perf=None, *args, **kwargs):
        super(ICouldBeRouterToNetwork, self).__init__(*args, **kwargs)

        self.npduNetMessage = ICouldBeRouterToNetwork.messageType
        self.icbrtnNetwork = net
        self.icbrtnPerformanceIndex = perf

    def encode(self, npdu):
        NPCI.update(npdu, self)
        npdu.put_short( self.icbrtnNetwork )
        npdu.put( self.icbrtnPerformanceIndex )

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.icbrtnNetwork = npdu.get_short()
        self.icbrtnPerformanceIndex = npdu.get()

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'ICouldBeRouterToNetwork'),
                ('network', self.icbrtnNetwork),
                ('performance_index', self.icbrtnPerformanceIndex),
            ))

register_npdu_type(ICouldBeRouterToNetwork)

#
#   RejectMessageToNetwork
#

class RejectMessageToNetwork(NPDU):

    _debug_contents = ('rmtnRejectReason','rmtnDNET')

    messageType = 0x03

    def __init__(self, reason=None, dnet=None, *args, **kwargs):
        super(RejectMessageToNetwork, self).__init__(*args, **kwargs)

        self.npduNetMessage = RejectMessageToNetwork.messageType
        self.rmtnRejectionReason = reason
        self.rmtnDNET = dnet

    def encode(self, npdu):
        NPCI.update(npdu, self)
        npdu.put( self.rmtnRejectionReason )
        npdu.put_short( self.rmtnDNET )

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.rmtnRejectionReason = npdu.get()
        self.rmtnDNET = npdu.get_short()

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'RejectMessageToNetwork'),
                ('reject_reason', self.rmtnRejectionReason),
                ('dnet', self.rmtnDNET),
            ))

register_npdu_type(RejectMessageToNetwork)

#
#   RouterBusyToNetwork
#

class RouterBusyToNetwork(NPDU):

    _debug_contents = ('rbtnNetworkList',)

    messageType = 0x04

    def __init__(self, netList=[], *args, **kwargs):
        super(RouterBusyToNetwork, self).__init__(*args, **kwargs)

        self.npduNetMessage = RouterBusyToNetwork.messageType
        self.rbtnNetworkList = netList

    def encode(self, npdu):
        NPCI.update(npdu, self)
        for net in self.ratnNetworkList:
            npdu.put_short(net)

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.rbtnNetworkList = []
        while npdu.pduData:
            self.rbtnNetworkList.append(npdu.get_short())

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'RouterBusyToNetwork'),
                ('network_list', self.rbtnNetworkList),
            ))

register_npdu_type(RouterBusyToNetwork)

#
#   RouterAvailableToNetwork
#

class RouterAvailableToNetwork(NPDU):

    _debug_contents = ('ratnNetworkList',)

    messageType = 0x05

    def __init__(self, netList=[], *args, **kwargs):
        super(RouterAvailableToNetwork, self).__init__(*args, **kwargs)

        self.npduNetMessage = RouterAvailableToNetwork.messageType
        self.ratnNetworkList = netList

    def encode(self, npdu):
        NPCI.update(npdu, self)
        for net in self.ratnNetworkList:
            npdu.put_short(net)

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.ratnNetworkList = []
        while npdu.pduData:
            self.ratnNetworkList.append(npdu.get_short())

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'RouterAvailableToNetwork'),
                ('network_list', self.ratnNetworkList),
            ))

register_npdu_type(RouterAvailableToNetwork)

#
#   Routing Table Entry
#

class RoutingTableEntry(DebugContents):

    _debug_contents = ('rtDNET', 'rtPortID', 'rtPortInfo')

    def __init__(self, dnet=None, portID=None, portInfo=None):
        self.rtDNET = dnet
        self.rtPortID = portID
        self.rtPortInfo = portInfo

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # save the content
        use_dict.__setitem__('dnet', self.rtDNET)
        use_dict.__setitem__('port_id', self.rtPortID)
        use_dict.__setitem__('port_info', self.rtPortInfo)

        # return what we built/updated
        return use_dict

#
#   InitializeRoutingTable
#

class InitializeRoutingTable(NPDU):
    messageType = 0x06
    _debug_contents = ('irtTable++',)

    def __init__(self, routingTable=[], *args, **kwargs):
        super(InitializeRoutingTable, self).__init__(*args, **kwargs)

        self.npduNetMessage = InitializeRoutingTable.messageType
        self.irtTable = routingTable

    def encode(self, npdu):
        NPCI.update(npdu, self)
        npdu.put(len(self.irtTable))
        for rte in self.irtTable:
            npdu.put_short(rte.rtDNET)
            npdu.put(rte.rtPortID)
            npdu.put(len(rte.rtPortInfo))
            npdu.put_data(rte.rtPortInfo)

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.irtTable = []

        rtLength = npdu.get()
        for i in range(rtLength):
            dnet = npdu.get_short()
            portID = npdu.get()
            portInfoLen = npdu.get()
            portInfo = npdu.get_data(portInfoLen)
            rte = RoutingTableEntry(dnet, portID, portInfo)
            self.irtTable.append(rte)

    def npdu_contents(self, use_dict=None, as_class=dict):
        routing_table = []
        for rte in self.irtTable:
            routing_table.append(rte.dict_contents(as_class=as_class))

        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'InitializeRoutingTable'),
                ('routing_table', routing_table),
            ))

register_npdu_type(InitializeRoutingTable)

#
#   InitializeRoutingTableAck
#

class InitializeRoutingTableAck(NPDU):
    messageType = 0x07
    _debug_contents = ('irtaTable++',)

    def __init__(self, routingTable=[], *args, **kwargs):
        super(InitializeRoutingTableAck, self).__init__(*args, **kwargs)

        self.npduNetMessage = InitializeRoutingTableAck.messageType
        self.irtaTable = routingTable

    def encode(self, npdu):
        NPCI.update(npdu, self)
        npdu.put(len(self.irtaTable))
        for rte in self.irtaTable:
            npdu.put_short(rte.rtDNET)
            npdu.put(rte.rtPortID)
            npdu.put(len(rte.rtPortInfo))
            npdu.put_data(rte.rtPortInfo)

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.irtaTable = []

        rtLength = npdu.get()
        for i in range(rtLength):
            dnet = npdu.get_short()
            portID = npdu.get()
            portInfoLen = npdu.get()
            portInfo = npdu.get_data(portInfoLen)
            rte = RoutingTableEntry(dnet, portID, portInfo)
            self.irtaTable.append(rte)

    def npdu_contents(self, use_dict=None, as_class=dict):
        routing_table = []
        for rte in self.irtaTable:
            routing_table.append(rte.dict_contents(as_class=as_class))

        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'InitializeRoutingTableAck'),
                ('routing_table', routing_table),
            ))

register_npdu_type(InitializeRoutingTableAck)

#
#   EstablishConnectionToNetwork
#

class EstablishConnectionToNetwork(NPDU):

    _debug_contents = ('ectnDNET', 'ectnTerminationTime')

    messageType = 0x08

    def __init__(self, dnet=None, terminationTime=None, *args, **kwargs):
        super(EstablishConnectionToNetwork, self).__init__(*args, **kwargs)

        self.npduNetMessage = EstablishConnectionToNetwork.messageType
        self.ectnDNET = dnet
        self.ectnTerminationTime = terminationTime

    def encode(self, npdu):
        NPCI.update(npdu, self)
        npdu.put_short( self.ectnDNET )
        npdu.put( self.ectnTerminationTime )

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.ectnDNET = npdu.get_short()
        self.ectnTerminationTime = npdu.get()

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'EstablishConnectionToNetwork'),
                ('dnet', self.ectnDNET),
                ('termination_time', self.ectnTerminationTime),
            ))

register_npdu_type(EstablishConnectionToNetwork)

#
#   DisconnectConnectionToNetwork
#

class DisconnectConnectionToNetwork(NPDU):

    _debug_contents = ('dctnDNET',)

    messageType = 0x09

    def __init__(self, dnet=None, *args, **kwargs):
        super(DisconnectConnectionToNetwork, self).__init__(*args, **kwargs)

        self.npduNetMessage = DisconnectConnectionToNetwork.messageType
        self.dctnDNET = dnet

    def encode(self, npdu):
        NPCI.update(npdu, self)
        npdu.put_short( self.dctnDNET )

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.dctnDNET = npdu.get_short()

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'DisconnectConnectionToNetwork'),
                ('dnet', self.dctnDNET),
            ))

register_npdu_type(DisconnectConnectionToNetwork)

#
#   WhatIsNetworkNumber
#

class WhatIsNetworkNumber(NPDU):

    _debug_contents = ()

    messageType = 0x12

    def encode(self, npdu):
        NPCI.update(npdu, self)

    def decode(self, npdu):
        NPCI.update(self, npdu)

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'WhatIsNetworkNumber'),
            ))

register_npdu_type(WhatIsNetworkNumber)

#
#   NetworkNumberIs
#

class NetworkNumberIs(NPDU):

    _debug_contents = ('nniNET', 'nniFlag',)

    messageType = 0x13

    def encode(self, npdu):
        NPCI.update(npdu, self)
        npdu.put_short( self.nniNET )
        npdu.put( self.nniFlag )

    def decode(self, npdu):
        NPCI.update(self, npdu)
        self.nniNET = npdu.get_short()
        self.nniFlag = npdu.get()

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(use_dict=use_dict, as_class=as_class,
            key_values=(
                ('function', 'NetorkNumberIs'),
                ('net', self.nniNET),
                ('flag', self.nniFlag),
            ))

register_npdu_type(NetworkNumberIs)

