#!/usr/bin/env python

import logging
from ..comm import Capability

from ..basetypes import ErrorType, PropertyIdentifier
from ..primitivedata import Atomic, Null, Unsigned
from ..constructeddata import Any, Array, ArrayOf

from ..apdu import SimpleAckPDU, ReadPropertyACK, ReadPropertyMultipleACK, \
    ReadAccessResult, ReadAccessResultElement, ReadAccessResultElementChoice
from ..errors import ExecutionError
from ..object import Property, Object, PropertyError

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = [
    'ReadWritePropertyServices', 'read_property_to_any', 'read_property_to_result_element',
    'ReadWritePropertyMultipleServices'
]
# handy reference
ArrayOfPropertyIdentifier = ArrayOf(PropertyIdentifier)


class ReadWritePropertyServices(Capability):
    """
    ReadProperty and WriteProperty Services
    """
    def __init__(self):
        if DEBUG: _logger.debug("__init__")
        Capability.__init__(self)

    def do_ReadPropertyRequest(self, apdu):
        """Return the value of some property of one of our objects."""
        if DEBUG: _logger.debug("do_ReadPropertyRequest %r", apdu)
        # extract the object identifier
        obj_id = apdu.objectIdentifier
        # check for wildcard
        if (obj_id == ('device', 4194303)) and self.localDevice is not None:
            if DEBUG: _logger.debug("    - wildcard device identifier")
            obj_id = self.localDevice.objectIdentifier
        # get the object
        obj = self.get_object_id(obj_id)
        if DEBUG: _logger.debug("    - object: %r", obj)
        if not obj:
            raise ExecutionError(errorClass='object', errorCode='unknownObject')
        try:
            # get the datatype
            datatype = obj.get_datatype(apdu.propertyIdentifier)
            if DEBUG: _logger.debug("    - datatype: %r", datatype)
            # get the value
            value = obj.ReadProperty(apdu.propertyIdentifier, apdu.propertyArrayIndex)
            if DEBUG: _logger.debug("    - value: %r", value)
            if value is None:
                raise PropertyError(apdu.propertyIdentifier)
            # change atomic values into something encodeable
            if issubclass(datatype, Atomic):
                value = datatype(value)
            elif issubclass(datatype, Array) and (apdu.propertyArrayIndex is not None):
                if apdu.propertyArrayIndex == 0:
                    value = Unsigned(value)
                elif issubclass(datatype.subtype, Atomic):
                    value = datatype.subtype(value)
                elif not isinstance(value, datatype.subtype):
                    raise TypeError("invalid result datatype, expecting {0} and got {1}" \
                                    .format(datatype.subtype.__name__, type(value).__name__))
            elif not isinstance(value, datatype):
                raise TypeError("invalid result datatype, expecting {0} and got {1}" \
                                .format(datatype.__name__, type(value).__name__))
            if DEBUG: _logger.debug("    - encodeable value: %r", value)
            # this is a ReadProperty ack
            resp = ReadPropertyACK(context=apdu)
            resp.objectIdentifier = obj_id
            resp.propertyIdentifier = apdu.propertyIdentifier
            resp.propertyArrayIndex = apdu.propertyArrayIndex
            # save the result in the property value
            resp.propertyValue = Any()
            resp.propertyValue.cast_in(value)
            if DEBUG: _logger.debug("    - resp: %r", resp)
        except PropertyError:
            raise ExecutionError(errorClass='property', errorCode='unknownProperty')
        # return the result
        self.response(resp)

    def do_WritePropertyRequest(self, apdu):
        """Change the value of some property of one of our objects."""
        if DEBUG: _logger.debug("do_WritePropertyRequest %r", apdu)
        # get the object
        obj = self.get_object_id(apdu.objectIdentifier)
        if DEBUG: _logger.debug("    - object: %r", obj)
        if not obj:
            raise ExecutionError(errorClass='object', errorCode='unknownObject')
        try:
            # check if the property exists
            if obj.ReadProperty(apdu.propertyIdentifier, apdu.propertyArrayIndex) is None:
                raise PropertyError(apdu.propertyIdentifier)
            # get the datatype, special case for null
            if apdu.propertyValue.is_application_class_null():
                datatype = Null
            else:
                datatype = obj.get_datatype(apdu.propertyIdentifier)
            if DEBUG: _logger.debug("    - datatype: %r", datatype)
            # special case for array parts, others are managed by cast_out
            if issubclass(datatype, Array) and (apdu.propertyArrayIndex is not None):
                if apdu.propertyArrayIndex == 0:
                    value = apdu.propertyValue.cast_out(Unsigned)
                else:
                    value = apdu.propertyValue.cast_out(datatype.subtype)
            else:
                value = apdu.propertyValue.cast_out(datatype)
            if DEBUG: _logger.debug("    - value: %r", value)
            # change the value
            obj.WriteProperty(apdu.propertyIdentifier, value, apdu.propertyArrayIndex, apdu.priority)
            # success
            resp = SimpleAckPDU(context=apdu)
            if DEBUG: _logger.debug("    - resp: %r", resp)
        except PropertyError:
            raise ExecutionError(errorClass='property', errorCode='unknownProperty')
        # return the result
        self.response(resp)


def read_property_to_any(obj, propertyIdentifier, propertyArrayIndex=None):
    """Read the specified property of the object, with the optional array index,
    and cast the result into an Any object."""
    if DEBUG: _logger.debug("read_property_to_any %s %r %r", obj, propertyIdentifier, propertyArrayIndex)
    # get the datatype
    datatype = obj.get_datatype(propertyIdentifier)
    if DEBUG: _logger.debug("    - datatype: %r", datatype)
    if datatype is None:
        raise ExecutionError(errorClass='property', errorCode='datatypeNotSupported')
    # get the value
    value = obj.ReadProperty(propertyIdentifier, propertyArrayIndex)
    if DEBUG: _logger.debug("    - value: %r", value)
    if value is None:
        raise ExecutionError(errorClass='property', errorCode='unknownProperty')
    # change atomic values into something encodeable
    if issubclass(datatype, Atomic):
        value = datatype(value)
    elif issubclass(datatype, Array) and (propertyArrayIndex is not None):
        if propertyArrayIndex == 0:
            value = Unsigned(value)
        elif issubclass(datatype.subtype, Atomic):
            value = datatype.subtype(value)
        elif not isinstance(value, datatype.subtype):
            raise TypeError("invalid result datatype, expecting %s and got %s" \
                            % (datatype.subtype.__name__, type(value).__name__))
    elif not isinstance(value, datatype):
        raise TypeError("invalid result datatype, expecting %s and got %s" \
                        % (datatype.__name__, type(value).__name__))
    if DEBUG: _logger.debug("    - encodeable value: %r", value)
    # encode the value
    result = Any()
    result.cast_in(value)
    if DEBUG: _logger.debug("    - result: %r", result)
    # return the object
    return result


def read_property_to_result_element(obj, propertyIdentifier, propertyArrayIndex=None):
    """Read the specified property of the object, with the optional array index,
    and cast the result into an Any object."""
    if DEBUG: _logger.debug("read_property_to_result_element %s %r %r", obj, propertyIdentifier, propertyArrayIndex)
    # save the result in the property value
    read_result = ReadAccessResultElementChoice()
    try:
        if not obj:
            raise ExecutionError(errorClass='object', errorCode='unknownObject')
        read_result.propertyValue = read_property_to_any(obj, propertyIdentifier, propertyArrayIndex)
        if DEBUG: _logger.debug("    - success")
    except PropertyError as error:
        if DEBUG: _logger.debug("    - error: %r", error)
        read_result.propertyAccessError = ErrorType(errorClass='property', errorCode='unknownProperty')
    except ExecutionError as error:
        if DEBUG: _logger.debug("    - error: %r", error)
        read_result.propertyAccessError = ErrorType(errorClass=error.errorClass, errorCode=error.errorCode)
    # make an element for this value
    read_access_result_element = ReadAccessResultElement(
        propertyIdentifier=propertyIdentifier,
        propertyArrayIndex=propertyArrayIndex,
        readResult=read_result,
    )
    if DEBUG: _logger.debug("    - read_access_result_element: %r", read_access_result_element)
    return read_access_result_element


class ReadWritePropertyMultipleServices(Capability):

    def __init__(self):
        if DEBUG: _logger.debug("__init__")
        Capability.__init__(self)

    def do_ReadPropertyMultipleRequest(self, apdu):
        """Respond to a ReadPropertyMultiple Request."""
        if DEBUG: _logger.debug("do_ReadPropertyMultipleRequest %r", apdu)
        # response is a list of read access results (or an error)
        resp = None
        read_access_result_list = []
        # loop through the request
        for read_access_spec in apdu.listOfReadAccessSpecs:
            # get the object identifier
            object_identifier = read_access_spec.objectIdentifier
            if DEBUG: _logger.debug("    - objectIdentifier: %r", object_identifier)
            # check for wildcard
            if (object_identifier == ('device', 4194303)) and self.localDevice is not None:
                if DEBUG: _logger.debug("    - wildcard device identifier")
                object_identifier = self.localDevice.objectIdentifier
            # get the object
            obj = self.get_object_id(object_identifier)
            if DEBUG: _logger.debug("    - object: %r", obj)
            # build a list of result elements
            read_access_result_element_list = []
            # loop through the property references
            for prop_reference in read_access_spec.listOfPropertyReferences:
                # get the property identifier
                property_identifier = prop_reference.propertyIdentifier
                if DEBUG: _logger.debug("    - propertyIdentifier: %r", property_identifier)
                # get the array index (optional)
                property_array_index = prop_reference.propertyArrayIndex
                if DEBUG: _logger.debug("    - propertyArrayIndex: %r", property_array_index)
                # check for special property identifiers
                if property_identifier in ('all', 'required', 'optional'):
                    if not obj:
                        # build a property access error
                        read_result = ReadAccessResultElementChoice()
                        read_result.propertyAccessError = ErrorType(errorClass='object', errorCode='unknownObject')
                        # make an element for this error
                        read_access_result_element = ReadAccessResultElement(
                            propertyIdentifier=property_identifier,
                            propertyArrayIndex=property_array_index,
                            readResult=read_result,
                        )
                        # add it to the list
                        read_access_result_element_list.append(read_access_result_element)
                    else:
                        for propId, prop in obj._properties.items():
                            if DEBUG: _logger.debug("    - checking: %r %r", propId,
                                                    prop.optional)
                            if property_identifier == 'all':
                                pass
                            elif (property_identifier == 'required') and prop.optional:
                                if DEBUG: _logger.debug("    - not a required property")
                                continue
                            elif (property_identifier == 'optional') and (not prop.optional):
                                if DEBUG: _logger.debug("    - not an optional property")
                                continue
                            # read the specific property
                            read_access_result_element = read_property_to_result_element(obj, propId,
                                                                                         property_array_index)
                            # check for undefined property
                            if read_access_result_element.readResult.propertyAccessError \
                                    and read_access_result_element.readResult.propertyAccessError.errorCode == 'unknownProperty':
                                continue
                            # add it to the list
                            read_access_result_element_list.append(read_access_result_element)
                else:
                    # read the specific property
                    read_access_result_element = read_property_to_result_element(obj, property_identifier,
                                                                                 property_array_index)
                    # add it to the list
                    read_access_result_element_list.append(read_access_result_element)
            # build a read access result
            read_access_result = ReadAccessResult(
                objectIdentifier=object_identifier,
                listOfResults=read_access_result_element_list
            )
            if DEBUG: _logger.debug("    - read_access_result: %r", read_access_result)
            # add it to the list
            read_access_result_list.append(read_access_result)
        # this is a ReadPropertyMultiple ack
        if not resp:
            resp = ReadPropertyMultipleACK(context=apdu)
            resp.listOfReadAccessResults = read_access_result_list
            if DEBUG: _logger.debug("    - resp: %r", resp)
        self.response(resp)
