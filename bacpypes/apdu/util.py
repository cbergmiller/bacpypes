
import logging
from .apdu import ReadPropertyACK, ReadPropertyMultipleACK, ReadAccessResultElement
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
        return _get_value_from_result(apdu, apdu.objectIdentifier[0])
    elif isinstance(apdu, ReadPropertyMultipleACK):
        values = {}
        for result in apdu.listOfReadAccessResults:
            # here is the object identifier
            object_type, object_id = result.objectIdentifier
            _logger.info('multi objectIdentifier %s %r', type(result.objectIdentifier), result.objectIdentifier)
            _v = values[f'{object_type}{object_id}'] = {}
            for element in result.listOfResults:
                _v[element.propertyIdentifier] = _get_value_from_result(element, object_type)
        return values
    raise ValueError('Unsupported apdu %r', apdu)


def _get_value_from_result(element, object_type):
    if isinstance(element, ReadAccessResultElement):
        prop_value = element.readResult.propertyValue
        if element.readResult.propertyAccessError:
            # ToDo: optionally throw
            return element.readResult.propertyAccessError
    elif isinstance(element, ReadPropertyACK):
        prop_value = element.propertyValue
    else:
        raise ValueError('Unsupported result element %r', element)
    data_type = get_datatype(object_type, element.propertyIdentifier)
    if not data_type:
        raise TypeError('unknown data_type')
    # special case for array parts, others are managed by cast_out
    if issubclass(data_type, Array) and (element.propertyArrayIndex is not None):
        if element.propertyArrayIndex == 0:
            return prop_value.cast_out(Unsigned)
        else:
            return prop_value.cast_out(data_type.subtype)
    return prop_value.cast_out(data_type)
