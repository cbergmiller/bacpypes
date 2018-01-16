from pprint import pprint
import logging
import asyncio

from bacpypes import Address, LoggingFormatter, ReadPropertyRequest, ReadPropertyMultipleRequest, \
    ReadAccessSpecification, PropertyReference, BIPSimpleApplication, LocalDeviceObject

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


async def read_object_name(app, device_id, addr):
    """
    Execute a single request using `ReadPropertyRequest`.
    This will read the `objectName` property of a remote device.
    :param app: An app instance
    :param device_id: BACnet device id (integer number)
    :param addr: The network address of the remote device
    :return: The object name value
    """
    return await app.execute_request(
        ReadPropertyRequest(
            objectIdentifier=('device', device_id),
            propertyIdentifier='objectName',
            destination=Address(addr)
        )
    )


async def read_analog_inputs(app, addr):
    """
    Execute a sequence of `ReadPropertyRequest`.
    This will read the first ten analog input values from the remote device.
    :param app: An app instance
    :param addr: The network address of the remote device
    :return: A list of analog input values
    """
    return await app.execute_requests(
        ReadPropertyRequest(
            objectIdentifier=('analogInput', i),
            propertyIdentifier='presentValue',
            destination=Address(addr)
        ) for i in range(10)
    )


async def read_multi_analog_inputs(app, addr):
    """
    Execute a single request using `ReadPropertyMultipleRequest`.
    This will read the first 40 analog input values from the remote device.
    :param app: An app instance
    :param addr: The network address of the remote device
    :return:
    """
    read_access_specs = []
    for i in range(10):
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


if __name__ == '__main__':
    # This represents the local device
    this_device = LocalDeviceObject(
        objectName='Test Device',
        objectIdentifier=599,
        maxApduLengthAccepted=1024,
        segmentationSupported='segmentedBoth',
        vendorIdentifier=15,
    )
    app = BIPSimpleApplication(this_device, '10.81.0.14')

    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    object_name = loop.run_until_complete(read_object_name(app, 881000, '192.168.2.70'))
    prop_values_1 = loop.run_until_complete(read_analog_inputs(app, '192.168.2.70'))
    prop_values_2 = loop.run_until_complete(read_multi_analog_inputs(app, '192.168.2.70'))
    loop.close()
    print(type(object_name))
    print(object_name)
    pprint(prop_values_1)
    pprint(prop_values_2)
