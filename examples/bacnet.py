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
_logger.setLevel(logging.WARNING)
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)
ch.setFormatter(LoggingFormatter('%(name)s - %(levelname)s - %(message)s'))
_logger.addHandler(ch)

_alogger = logging.getLogger('asyncio')
_alogger.setLevel(logging.INFO)
ach = logging.StreamHandler()
ach.setLevel(logging.INFO)
ach.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
_alogger.addHandler(ach)


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


async def discover_properties(app, device_id, addr):
    objects = await app.execute_request(
        ReadPropertyRequest(
            objectIdentifier=('device', device_id),
            propertyIdentifier='objectList',
            destination=Address(addr)
        )
    )
    result = {}
    for object_identifier in objects:
        _logger.info(object_identifier)
        read_access_specs = [
            ReadAccessSpecification(
                objectIdentifier=object_identifier,
                listOfPropertyReferences=[
                    PropertyReference(propertyIdentifier='presentValue'),
                    PropertyReference(propertyIdentifier='objectName'),
                    PropertyReference(propertyIdentifier='objectType'),
                    PropertyReference(propertyIdentifier='description'),
                    PropertyReference(propertyIdentifier='units'),
                ],
            ),
        ]
        result.update(
            await app.execute_request(
                ReadPropertyMultipleRequest(
                    listOfReadAccessSpecs=read_access_specs,
                    destination=Address(addr)
                ),
            )
        )
    global properties
    properties = result
    asyncio.get_event_loop().stop()


if __name__ == '__main__':
    # This represents the local device
    this_device = LocalDeviceObject(
        objectName='Energy Box',
        objectIdentifier=599,
        maxApduLengthAccepted=1024,
        segmentationSupported='segmentedBoth',
        vendorIdentifier=15,
    )
    app = BIPSimpleApplication(this_device, '192.168.2.109')

    # get the services supported
    services_supported = app.get_services_supported()
    _logger.info('    - services_supported: %s', services_supported)
    # this_device.protocolServicesSupported = services_supported.value

    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    host = '192.168.2.16'

    # loop.create_task(read_device_props(app, 881000, host))
    properties = None
    loop.create_task(discover_properties(app, 123, host))

    loop.run_forever()

    # prop_values = loop.run_until_complete(read_prop_values(app, host))

    # pprint(properties)
    for key, prop in properties.items():
        if prop['objectType'] == 'device':
            continue
        print(f'{key:<24}{prop["objectName"]!s:40.40}{prop["description"]!s:60.60} {prop["presentValue"]} {prop["units"]}')
