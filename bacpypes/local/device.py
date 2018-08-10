#!/usr/bin/env python

import logging

from ..primitivedata import Date, Time, ObjectIdentifier
from ..constructeddata import ArrayOf
from ..basetypes import ServicesSupported

from ..errors import ExecutionError
from ..object import register_object_type, registered_object_types, \
    Property, DeviceObject

from .object import CurrentPropertyListMixIn

# some debugging
DEBUG = 0
_log = logging.getLogger(__name__)


class CurrentLocalDate(Property):

    def __init__(self):
        Property.__init__(self, 'localDate', Date, default=(), optional=True, mutable=False)

    def ReadProperty(self, obj, arrayIndex=None):
        if arrayIndex is not None:
            raise ExecutionError(errorClass='property', errorCode='propertyIsNotAnArray')

        # get the value
        now = Date()
        now.now()
        return now.value

    def WriteProperty(self, obj, value, arrayIndex=None, priority=None, direct=False):
        raise ExecutionError(errorClass='property', errorCode='writeAccessDenied')


class CurrentLocalTime(Property):

    def __init__(self):
        Property.__init__(self, 'localTime', Time, default=(), optional=True, mutable=False)

    def ReadProperty(self, obj, arrayIndex=None):
        if arrayIndex is not None:
            raise ExecutionError(errorClass='property', errorCode='propertyIsNotAnArray')

        # get the value
        now = Time()
        now.now()
        return now.value

    def WriteProperty(self, obj, value, arrayIndex=None, priority=None, direct=False):
        raise ExecutionError(errorClass='property', errorCode='writeAccessDenied')


class CurrentProtocolServicesSupported(Property):

    def __init__(self):
        if DEBUG: _log.debug("__init__")
        Property.__init__(self, 'protocolServicesSupported', ServicesSupported, default=None, optional=True, mutable=False)

    def ReadProperty(self, obj, arrayIndex=None):
        if DEBUG: _log.debug("ReadProperty %r %r", obj, arrayIndex)

        # not an array
        if arrayIndex is not None:
            raise ExecutionError(errorClass='property', errorCode='propertyIsNotAnArray')

        # return what the application says
        return obj._app.get_services_supported()

    def WriteProperty(self, obj, value, arrayIndex=None, priority=None, direct=False):
        raise ExecutionError(errorClass='property', errorCode='writeAccessDenied')


class LocalDeviceObject(CurrentPropertyListMixIn, DeviceObject):

    properties = [
        CurrentLocalTime(),
        CurrentLocalDate(),
        CurrentProtocolServicesSupported(),
    ]

    defaultProperties = {
        'maxApduLengthAccepted': 1024,
        'segmentationSupported': 'segmentedBoth',
        'maxSegmentsAccepted': 16,
        'apduSegmentTimeout': 5000,
        'apduTimeout': 3000,
        'numberOfApduRetries': 3,
    }

    def __init__(self, **kwargs):
        if DEBUG: _log.debug("__init__ %r", kwargs)

        # fill in default property values not in kwargs
        for attr, value in LocalDeviceObject.defaultProperties.items():
            if attr not in kwargs:
                kwargs[attr] = value

        for key, value in kwargs.items():
            if key.startswith("_"):
                setattr(self, key, value)
                del kwargs[key]

        # check for registration
        if self.__class__ not in registered_object_types.values():
            if 'vendorIdentifier' not in kwargs:
                raise RuntimeError("vendorIdentifier required to auto-register the LocalDeviceObject class")
            register_object_type(self.__class__, vendor_id=kwargs['vendorIdentifier'])

        # check for properties this class implements
        if 'localDate' in kwargs:
            raise RuntimeError("localDate is provided by LocalDeviceObject and cannot be overridden")
        if 'localTime' in kwargs:
            raise RuntimeError("localTime is provided by LocalDeviceObject and cannot be overridden")
        if 'protocolServicesSupported' in kwargs:
            raise RuntimeError("protocolServicesSupported is provided by LocalDeviceObject and cannot be overridden")

        # the object identifier is required for the object list
        if 'objectIdentifier' not in kwargs:
            raise RuntimeError("objectIdentifier is required")

        # coerce the object identifier
        object_identifier = kwargs['objectIdentifier']
        if isinstance(object_identifier, int):
            object_identifier = ('device', object_identifier)

        # the object list is provided
        if 'objectList' in kwargs:
            raise RuntimeError("objectList is provided by LocalDeviceObject and cannot be overridden")
        kwargs['objectList'] = ArrayOf(ObjectIdentifier)([object_identifier])

        # check for a minimum value
        if kwargs['maxApduLengthAccepted'] < 50:
            raise ValueError("invalid max APDU length accepted")

        # dump the updated attributes
        if DEBUG: _log.debug("    - updated kwargs: %r", kwargs)

        # proceed as usual
        super(LocalDeviceObject, self).__init__(**kwargs)
