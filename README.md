# Asnyc. BACpypes

This is a diverging fork of the BACpypes python package.

## Development goals

- Removal of asyncore dependecy and the bacpypes.core event loop in favour of asyncio
- Refactored project structure (one class per module where feasible)
- Reduction of multiple inheritance and overall amount of code (for easier maintenance)
- PEP8 compliant code refactoring
- Simplified asynchronous application API

This package will only run at Python 3.6 and above.

## State of Development

### What works so far

- `BIPSimpleApplication` reading properties

### Still to be tested/refactored/implemented

- `COVSubscription`
- `BIPForeignApplication`
- The TCP stack

## Installation

This fork ist not uploaded to PIP but you can install it like this: 

```cmd
pip install git+https://github.com/cbegmiller/bacpypes
```

## Usage

```python
from asyncio import get_event_loop
from bacpypes.link import Address
from bacpypes.apdu import ReadPropertyRequest, ReadPropertyMultipleRequest
from bacpypes.app import BIPSimpleApplication
from bacpypes.service.device import LocalDeviceObject

async def read_device_properties(app, device_id, remote_addr):
    result = await app.execute_requests(
        ReadPropertyRequest(
            objectIdentifier=('device', device_id),
            propertyIdentifier=property_id,
            destination=Address(remote_addr)
        ) for property_id in ['objectName', 'modelName', 'vendorName', 'serialNumber', 'objectList']
    )
    return result 
    
this_device = LocalDeviceObject(
    objectName='Energy Box',
    objectIdentifier=599,
    maxApduLengthAccepted=1024,
    segmentationSupported='segmentedBoth',
    vendorIdentifier=15,
)

app = BIPSimpleApplication(this_device, '192.168.2.123')
loop = get_event_loop()
result = loop.run_until_complete(read_device_properties(app, 88100, '192.168.2.70'))
loop.close()
print(result)
```