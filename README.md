# Asnyc. BACpypes

This is a diverging fork of the BACpypes python package.

## Development goals

- Removal of asyncore dependecy and the bacpypes.core event loop in favour of asyncio
- Refactored project structure (one class per module where feasible)
- Reduction of multiple inheritance and overall amount of code (for easier maintenance)
- PEP8 compliant code
- Simplified asynchronous API

This package will only be compatible at Python 3.6 and above.

## State of Development

### What works so far

- `BIPSimpleApplication` reading properties

### Still to be tested/refactored/implemented

- `COVSubscription`
- `BIPForeignApplication`
- The TCP stack

## Installation

This fork ist not uploaded to PyPI but you can install it like this: 

```cmd
pip install git+https://github.com/cbergmiller/bacpypes
```

## Usage

### High level API
```python

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
    app = BIPSimpleApplication(this_device, '192.168.1.2')
    loop = asyncio.get_event_loop()
    analog_value = loop.run_until_complete(read_analog_value(app, '192.168.1.3'))
    loop.close()
    print(analog_value)

```