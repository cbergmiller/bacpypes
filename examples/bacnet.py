#!/usr/bin/env python

"""
Mutliple Read Property

This application has a static list of points that it would like to read.  It reads the
values of each of them in turn and then quits.
"""

from pprint import pprint
import logging
import asyncio

from bacpypes.comm import IOCB
from bacpypes.link import Address
from bacpypes.object import get_datatype
from bacpypes.debugging import LoggingFormatter
from bacpypes.apdu import ReadPropertyRequest, ReadPropertyMultipleRequest, ReadAccessSpecification, PropertyReference, \
    ReadPropertyACK
from bacpypes.primitivedata import Unsigned
from bacpypes.constructeddata import Array

from bacpypes.app import BIPSimpleApplication
from bacpypes.service.device import LocalDeviceObject

_logger = logging.getLogger('bacpypes')
_logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(LoggingFormatter('%(name)s - %(levelname)s - %(message)s'))
_logger.addHandler(ch)

_alogger = logging.getLogger('asyncio')
_alogger.setLevel(logging.DEBUG)
ach = logging.StreamHandler()
ach.setLevel(logging.DEBUG)
ach.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
_alogger.addHandler(ach)


class ReadPointListApplication(BIPSimpleApplication):
    def __init__(self, points, *args):
        BIPSimpleApplication.__init__(self, *args)
        # turn the point list into a queue
        self.points = points
        # make a list of the response values
        self.device_properties = {}
        self.response_values = {}

    def complete_device_request(self, iocb):
        if iocb.io_error:
            _logger.debug("    - io error: %r", iocb.io_error)
            # do something for success
        elif iocb.io_response:
            apdu = iocb.io_response
            # should be an ack
            if not isinstance(apdu, ReadPropertyACK):
                _logger.debug("    - not an ack")
                return
            # find the datatype
            datatype = get_datatype(apdu.objectIdentifier[0], apdu.propertyIdentifier)
            _logger.debug("    - datatype: %r", datatype)
            if not datatype:
                raise TypeError("unknown datatype")
            # special case for array parts, others are managed by cast_out
            if issubclass(datatype, Array) and (apdu.propertyArrayIndex is not None):
                if apdu.propertyArrayIndex == 0:
                    value = apdu.propertyValue.cast_out(Unsigned)
                else:
                    value = apdu.propertyValue.cast_out(datatype.subtype)
            else:
                value = apdu.propertyValue.cast_out(datatype)
            _logger.debug("    - value: %r", value)
            self.device_properties[apdu.propertyIdentifier] = value
        else:
            _logger.debug("    - ioError or ioResponse expected")

    def do_multi_request(self, addr):
        _logger.debug('do_request')

        read_access_specs = []
        for obj_type, obj_inst, prop_ids in self.points:
            read_access_specs.append(
                ReadAccessSpecification(
                    objectIdentifier=(obj_type, obj_inst),
                    listOfPropertyReferences=[PropertyReference(propertyIdentifier=id) for id in prop_ids],
                )
            )
        request = ReadPropertyMultipleRequest(listOfReadAccessSpecs=read_access_specs)
        request.pduDestination = Address(addr)
        _logger.debug('    - request: %r', request)
        # make an IOCB
        iocb = IOCB(request)
        # set a callback for the response
        iocb.add_callback(self.complete_multi_request)
        _logger.debug("    - iocb: %r", iocb)
        # send the request
        self.request_io(iocb)

    def complete_multi_request(self, iocb):
        _logger.debug("complete_multi_request %r", iocb)
        if iocb.io_response:
            apdu = iocb.io_response
            # loop through the results
            for result in apdu.listOfReadAccessResults:
                # here is the object identifier
                object_identifier = result.objectIdentifier
                self.response_values[object_identifier] = {}
                # _logger.debug("    - objectIdentifier: %r", object_identifier)
                # now come the property values per object
                for element in result.listOfResults:
                    # get the property and array index
                    property_identifier = element.propertyIdentifier
                    # _logger.debug("    - propertyIdentifier: %r", property_identifier)
                    property_array_index = element.propertyArrayIndex
                    # _logger.debug("    - propertyArrayIndex: %r", property_array_index)
                    # here is the read result
                    read_result = element.readResult
                    # check for an error
                    if read_result.propertyAccessError is not None:
                        self.response_values[object_identifier][
                            property_identifier] = f'! {read_result.propertyAccessError}'
                    else:
                        # here is the value
                        property_value = read_result.propertyValue
                        # find the datatype
                        datatype = get_datatype(object_identifier[0], property_identifier)
                        # _logger.debug("    - datatype: %r", datatype)
                        if not datatype:
                            raise TypeError("unknown datatype")

                        # special case for array parts, others are managed by cast_out
                        if issubclass(datatype, Array) and (property_array_index is not None):
                            if property_array_index == 0:
                                value = property_value.cast_out(Unsigned)
                            else:
                                value = property_value.cast_out(datatype.subtype)
                        else:
                            value = property_value.cast_out(datatype)
                        self.response_values[object_identifier][property_identifier] = value
        if iocb.io_error:
            _logger.debug("    - error: %r", iocb.io_error)
        asyncio.get_event_loop().stop()


async def read_device_props(app, device_id, addr):
    return await app.execute_requests(
        ReadPropertyRequest(
            objectIdentifier=('device', device_id),
            propertyIdentifier=property_id,
            destination=Address(addr)
        ) for property_id in ['objectName', 'modelName', 'vendorName', 'serialNumber', 'objectList']
    )


async def read_prop_values(app, addr):
    read_access_specs = []
    for i in range(40):
        read_access_specs.append(
            ReadAccessSpecification(
                objectIdentifier=('analogInput', i),
                listOfPropertyReferences=[PropertyReference(propertyIdentifier='presentValue')],
            )
        )
    return await app.execute_request(
        ReadPropertyMultipleRequest(
            listOfReadAccessSpecs=read_access_specs,
            destination=Address(addr)
        ),
    )


def main():
    # make a device object
    this_device = LocalDeviceObject(
        objectName='Energy Box',
        objectIdentifier=599,
        maxApduLengthAccepted=1024,
        segmentationSupported='segmentedBoth',
        vendorIdentifier=15,
    )

    app = BIPSimpleApplication(this_device, '10.81.0.14')

    # get the services supported
    services_supported = app.get_services_supported()
    _logger.debug(f'    - services_supported: {services_supported}')
    this_device.protocolServicesSupported = services_supported.value

    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    device_values = loop.run_until_complete(read_device_props(app, 881000, '192.168.2.70'))
    prop_values = loop.run_until_complete(read_prop_values(app, '192.168.2.70'))
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()

    # dump out the results
    pprint(device_values)
    pprint(prop_values)


if __name__ == '__main__':
    main()
