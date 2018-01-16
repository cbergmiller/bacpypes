from pprint import pprint
import logging
import asyncio
from functools import partial

from bacpypes import Address, LoggingFormatter, ReadPropertyRequest, ReadPropertyMultipleRequest, \
    ReadAccessSpecification, PropertyReference, BIPSimpleApplication, LocalDeviceObject

_logger = logging.getLogger('bacpypes')
_logger.setLevel(logging.DEBUG)
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
    loop.call_soon(app.who_is)
    try:
        loop.run_forever()
    except Exception:
        loop.close()
