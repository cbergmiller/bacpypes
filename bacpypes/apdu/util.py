
import logging
from .apdu import ReadPropertyACK, ReadPropertyMultipleACK
from ..object import get_datatype
from ..primitivedata import Unsigned
from ..constructeddata import Array

_logger = logging.getLogger(__name__)


def get_apdu_value(apdu):
    """
    Return the value of an apdu as primitive python type
    :param apdu:
    :return:
    """
    if isinstance(apdu, ReadPropertyACK):
        _logger.info('objectIdentifier %s %r', type(apdu.objectIdentifier), apdu.objectIdentifier)
        data_type = get_datatype(apdu.objectIdentifier[0], apdu.propertyIdentifier)
        if not data_type:
            raise TypeError('unknown data_type')
        # special case for array parts, others are managed by cast_out
        if issubclass(data_type, Array) and (apdu.propertyArrayIndex is not None):
            if apdu.propertyArrayIndex == 0:
                return apdu.propertyValue.cast_out(Unsigned)
            else:
                return apdu.propertyValue.cast_out(data_type.subtype)
        return apdu.propertyValue.cast_out(data_type)
    elif isinstance(apdu, ReadPropertyMultipleACK):
        values = {}
        for result in apdu.listOfReadAccessResults:
            # here is the object identifier
            object_identifier = result.objectIdentifier
            _logger.info('multi objectIdentifier %s %r', type(result.objectIdentifier), result.objectIdentifier)
            values[object_identifier] = {}
            for element in result.listOfResults:
                property_identifier = element.propertyIdentifier
                property_array_index = element.propertyArrayIndex
                # here is the read result
                read_result = element.readResult
                # check for an error
                if read_result.propertyAccessError is not None:
                    values[object_identifier][property_identifier] = f'! {read_result.propertyAccessError}'
                else:
                    # here is the value
                    property_value = read_result.propertyValue
                    data_type = get_datatype(object_identifier[0], property_identifier)
                    if not data_type:
                        raise TypeError('unknown datatype')
                    # special case for array parts, others are managed by cast_out
                    if issubclass(data_type, Array) and (property_array_index is not None):
                        if property_array_index == 0:
                            value = property_value.cast_out(Unsigned)
                        else:
                            value = property_value.cast_out(data_type.subtype)
                    else:
                        value = property_value.cast_out(data_type)
                values[object_identifier][property_identifier] = value
        return values
