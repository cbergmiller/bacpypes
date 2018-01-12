
import asyncio
from bacpypes import Address, ReadPropertyRequest, BIPSimpleApplication, LocalDeviceObject


async def read_analog_value(app, addr):
    """
    Execute a single request using `ReadPropertyRequest`.
    This will read a `analogValue` property of a remote device.
    :param app: An app instance
    :param addr: The network address of the remote device
    :return: The analog value
    """
    return await app.execute_request(
        ReadPropertyRequest(
            objectIdentifier=('analogInput', 0),
            propertyIdentifier='presentValue',
            destination=Address(addr)
        )
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
    app = BIPSimpleApplication(this_device, '192.168.2.109')
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    analog_value = loop.run_until_complete(read_analog_value(app, '192.168.2.70'))
    loop.close()
    print(analog_value)
