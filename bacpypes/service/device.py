#!/usr/bin/env python

import logging
from ..comm import Capability
from ..link import GlobalBroadcast
from ..apdu import WhoIsRequest, IAmRequest, IHaveRequest, SimpleAckPDU
from ..errors import ExecutionError, InconsistentParameters, \
    MissingRequiredParameter, ParameterOutOfRange
from ..task import call_later

_logger = logging.getLogger(__name__)
__all__ = ['WhoIsIAmServices', 'WhoHasIHaveServices', 'DeviceCommunicationControlServices']


class WhoIsIAmServices(Capability):

    def __init__(self):
        _logger.debug("__init__")
        Capability.__init__(self)

    def who_is(self, low_limit=None, high_limit=None, address=None):
        _logger.debug("who_is")
        # build a request
        who_is = WhoIsRequest()
        # defaults to a global broadcast
        if not address:
            address = GlobalBroadcast()
        # set the destination
        who_is.pduDestination = address
        # check for consistent parameters
        if low_limit is not None:
            if high_limit is None:
                raise MissingRequiredParameter("high_limit required")
            if (low_limit < 0) or (low_limit > 4194303):
                raise ParameterOutOfRange("low_limit out of range")
            # low limit is fine
            who_is.deviceInstanceRangeLowLimit = low_limit
        if high_limit is not None:
            if low_limit is None:
                raise MissingRequiredParameter("low_limit required")
            if (high_limit < 0) or (high_limit > 4194303):
                raise ParameterOutOfRange("high_limit out of range")
            # high limit is fine
            who_is.deviceInstanceRangeHighLimit = high_limit
        _logger.debug("    - who_is: %r", who_is)
        ### put the parameters someplace where they can be matched when the
        ### appropriate I-Am comes in
        # away it goes
        self.request(who_is)

    def do_WhoIsRequest(self, apdu):
        """Respond to a Who-Is request."""
        _logger.debug("do_WhoIsRequest %r", apdu)
        # ignore this if there's no local device
        if not self.localDevice:
            _logger.debug("    - no local device")
            return
        # extract the parameters
        low_limit = apdu.deviceInstanceRangeLowLimit
        high_limit = apdu.deviceInstanceRangeHighLimit
        # check for consistent parameters
        if low_limit is not None:
            if high_limit is None:
                raise MissingRequiredParameter("deviceInstanceRangeHighLimit required")
            if (low_limit < 0) or (low_limit > 4194303):
                raise ParameterOutOfRange("deviceInstanceRangeLowLimit out of range")
        if (high_limit is not None):
            if (low_limit is None):
                raise MissingRequiredParameter("deviceInstanceRangeLowLimit required")
            if (high_limit < 0) or (high_limit > 4194303):
                raise ParameterOutOfRange("deviceInstanceRangeHighLimit out of range")
        # see we should respond
        if low_limit is not None:
            if self.localDevice.objectIdentifier[1] < low_limit:
                return
        if high_limit is not None:
            if self.localDevice.objectIdentifier[1] > high_limit:
                return
        # generate an I-Am
        self.i_am(address=apdu.pduSource)

    def i_am(self, address=None):
        _logger.debug("i_am")
        # this requires a local device
        if not self.localDevice:
            _logger.debug("    - no local device")
            return
        # create a I-Am "response" back to the source
        i_am = IAmRequest(
            iAmDeviceIdentifier=self.localDevice.objectIdentifier,
            maxAPDULengthAccepted=self.localDevice.maxApduLengthAccepted,
            segmentationSupported=self.localDevice.segmentationSupported,
            vendorID=self.localDevice.vendorIdentifier,
        )
        # defaults to a global broadcast
        if not address:
            address = GlobalBroadcast()
        i_am.pduDestination = address
        _logger.debug("    - i_am: %r", i_am)
        # away it goes
        self.request(i_am)

    def do_IAmRequest(self, apdu):
        """Respond to an I-Am request."""
        _logger.debug("do_IAmRequest %r", apdu)
        # check for required parameters
        if apdu.iAmDeviceIdentifier is None:
            raise MissingRequiredParameter("iAmDeviceIdentifier required")
        if apdu.maxAPDULengthAccepted is None:
            raise MissingRequiredParameter("maxAPDULengthAccepted required")
        if apdu.segmentationSupported is None:
            raise MissingRequiredParameter("segmentationSupported required")
        if apdu.vendorID is None:
            raise MissingRequiredParameter("vendorID required")
        # extract the device instance number
        device_instance = apdu.iAmDeviceIdentifier[1]
        _logger.debug("    - device_instance: %r", device_instance)
        # extract the source address
        device_address = apdu.pduSource
        _logger.debug("    - device_address: %r", device_address)
        ### check to see if the application is looking for this device
        ### and update the device info cache if it is


class WhoHasIHaveServices(Capability):

    def __init__(self):
        _logger.debug("__init__")
        Capability.__init__(self)

    def who_has(self, thing, address=None):
        _logger.debug("who_has %r address=%r", thing, address)
        raise NotImplementedError("who_has")

    def do_WhoHasRequest(self, apdu):
        """Respond to a Who-Has request."""
        _logger.debug("do_WhoHasRequest, %r", apdu)
        # ignore this if there's no local device
        if not self.localDevice:
            _logger.debug("    - no local device")
            return
        # if this has limits, check them like Who-Is
        if apdu.limits is not None:
            # extract the parameters
            low_limit = apdu.limits.deviceInstanceRangeLowLimit
            high_limit = apdu.limits.deviceInstanceRangeHighLimit
            # check for consistent parameters
            if low_limit is None:
                raise MissingRequiredParameter("deviceInstanceRangeLowLimit required")
            if (low_limit < 0) or (low_limit > 4194303):
                raise ParameterOutOfRange("deviceInstanceRangeLowLimit out of range")
            if high_limit is None:
                raise MissingRequiredParameter("deviceInstanceRangeHighLimit required")
            if (high_limit < 0) or (high_limit > 4194303):
                raise ParameterOutOfRange("deviceInstanceRangeHighLimit out of range")
            # see we should respond
            if self.localDevice.objectIdentifier[1] < low_limit:
                return
            if self.localDevice.objectIdentifier[1] > high_limit:
                return
        # find the object
        if apdu.object.objectIdentifier is not None:
            obj = self.objectIdentifier.get(apdu.object.objectIdentifier, None)
        elif apdu.object.objectName is not None:
            obj = self.objectName.get(apdu.object.objectName, None)
        else:
            raise InconsistentParameters("object identifier or object name required")
        # maybe we don't have it
        if not obj:
            return
        # send out the response
        self.i_have(obj, address=apdu.pduSource)

    def i_have(self, thing, address=None):
        _logger.debug("i_have %r address=%r", thing, address)
        # ignore this if there's no local device
        if not self.localDevice:
            _logger.debug("    - no local device")
            return
        # build the request
        i_have = IHaveRequest(
            deviceIdentifier=self.localDevice.objectIdentifier,
            objectIdentifier=thing.objectIdentifier,
            objectName=thing.objectName,
        )
        # defaults to a global broadcast
        if not address:
            address = GlobalBroadcast()
        i_have.pduDestination = address
        _logger.debug("    - i_have: %r", i_have)
        # send it along
        self.request(i_have)

    def do_IHaveRequest(self, apdu):
        """Respond to a I-Have request."""
        _logger.debug("do_IHaveRequest %r", apdu)
        # check for required parameters
        if apdu.deviceIdentifier is None:
            raise MissingRequiredParameter("deviceIdentifier required")
        if apdu.objectIdentifier is None:
            raise MissingRequiredParameter("objectIdentifier required")
        if apdu.objectName is None:
            raise MissingRequiredParameter("objectName required")
        ### check to see if the application is looking for this object


class DeviceCommunicationControlServices(Capability):

    def __init__(self):
        _logger.debug("__init__")
        Capability.__init__(self)
        # task to run if there is a time duration
        self._dcc_enable_handle = None

    def do_DeviceCommunicationControlRequest(self, apdu):
        _logger.debug("do_CommunicationControlRequest, %r", apdu)
        if getattr(self.localDevice, "_dcc_password", None):
            if not apdu.password or apdu.password != getattr(self.localDevice, "_dcc_password"):
                raise ExecutionError(errorClass="security", errorCode="passwordFailure")
        if apdu.enableDisable == "enable":
            self.enable_communications()
        else:
            # disable or disableInitiation
            self.disable_communications(apdu.enableDisable)
            # if there is a time duration, it's in minutes
            if apdu.timeDuration:
                self._dcc_enable_handle = call_later(apdu.timeDuration * 60, self.enable_communications)
                _logger.debug("    - enable scheduled")
        # respond with a simple ack
        self.response(SimpleAckPDU(context=apdu))

    def enable_communications(self):
        _logger.debug("enable_communications")
        # tell the State Machine Access Point
        self.smap.dccEnableDisable = 'enable'
        # if an enable task was scheduled, cancel it
        if self._dcc_enable_handle:
            self._dcc_enable_handle.suspend_task()
            self._dcc_enable_handle = None

    def disable_communications(self, enable_disable):
        _logger.debug("disable_communications %r", enable_disable)
        # tell the State Machine Access Point
        self.smap.dccEnableDisable = enable_disable
        # if an enable task was scheduled, cancel it
        if self._dcc_enable_handle:
            self._dcc_enable_handle.suspend_task()
            self._dcc_enable_handle = None
