#!/usr/bin/env python

"""
Mutliple Read Property

This application has a static list of points that it would like to read.  It reads the
values of each of them in turn and then quits.
"""

import logging
import asyncio

from bacpypes.link import Address
from bacpypes.debugging import LoggingFormatter
from bacpypes.apdu import ReadPropertyRequest, ReadPropertyMultipleRequest, ReadAccessSpecification, PropertyReference

from bacpypes.app import BIPSimpleApplication
from bacpypes.local.device import LocalDeviceObject

_logger = logging.getLogger('bacpypes')
_logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
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
        ), throw_on_error=True
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
    host = '192.168.2.70'
    device_id = 881000
    loop.run_until_complete(app.create_endoint())
    # loop.create_task(read_device_props(app, device_id, host))
    properties = None
    loop.run_until_complete(discover_properties(app, device_id, host))
    loop.close()
    # prop_values = loop.run_until_complete(read_prop_values(app, host))
    # pprint(properties)

    for key, prop in properties.items():
        if prop['objectType'] == 'device':
            continue
        print(f'{key:<24}{prop["objectName"]!s:40.40}{prop["description"]!s:60.60} {prop["presentValue"]} {prop["units"]}')
