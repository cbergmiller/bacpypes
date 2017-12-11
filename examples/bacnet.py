#!/usr/bin/env python

"""
Mutliple Read Property

This application has a static list of points that it would like to read.  It reads the
values of each of them in turn and then quits.
"""

from collections import deque
import pprint
from bacpypes.debugging import bacpypes_debugging, ModuleLogger
from bacpypes.consolelogging import ConsoleLogHandler

from bacpypes.core import run, stop, deferred
from bacpypes.iocb import IOCB

from bacpypes.pdu import Address
from bacpypes.object import get_datatype

from bacpypes.apdu import ReadPropertyRequest, ReadPropertyMultipleRequest, ReadAccessSpecification, PropertyReference, ReadPropertyACK
from bacpypes.primitivedata import Unsigned
from bacpypes.constructeddata import Array

from bacpypes.app import BIPSimpleApplication
from bacpypes.service.device import LocalDeviceObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())
# ConsoleLogHandler(__name__)

@bacpypes_debugging
class ReadPointListApplication(BIPSimpleApplication):
    def __init__(self, points, *args):
        BIPSimpleApplication.__init__(self, *args)
        # turn the point list into a queue
        self.points = points
        # make a list of the response values
        self.device_properties = {}
        self.response_values = {}

    def do_device_request(self, device_id, addr):
        if _debug:
            ReadPointListApplication._debug("    - do_device_request: {} {}".format(device_id, addr))
        for property_id in ['objectName',  'modelName', 'vendorName', 'serialNumber', 'objectList']:
            request = ReadPropertyRequest(
                objectIdentifier=('device', device_id),
                propertyIdentifier=property_id,
            )
            request.pduDestination = Address(addr)
            iocb = IOCB(request)
            self.request_io(iocb)
            iocb.add_callback(self.complete_device_request)

    def complete_device_request(self, iocb):
        if iocb.ioError:
            if _debug:
                ReadPointListApplication._debug("    - error: %r", iocb.ioError)
            # do something for success
        elif iocb.ioResponse:
            apdu = iocb.ioResponse
            # should be an ack
            if not isinstance(apdu, ReadPropertyACK):
                if _debug: ReadPointListApplication._debug("    - not an ack")
                return
            # find the datatype
            datatype = get_datatype(apdu.objectIdentifier[0], apdu.propertyIdentifier)
            if _debug: ReadPointListApplication._debug("    - datatype: %r", datatype)
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
            if _debug: ReadPointListApplication._debug("    - value: %r", value)
            self.device_properties[apdu.propertyIdentifier] = value
        else:
            if _debug: ReadPointListApplication._debug("    - ioError or ioResponse expected")

    def do_multi_request(self):
        if _debug:
            ReadPointListApplication._debug('do_request')

        read_access_specs = []
        for obj_type, obj_inst, prop_ids in self.points:
            read_access_specs.append(
                ReadAccessSpecification(
                    objectIdentifier=(obj_type, obj_inst),
                    listOfPropertyReferences=[PropertyReference(propertyIdentifier=id) for id in prop_ids],
                )
            )
        request = ReadPropertyMultipleRequest(listOfReadAccessSpecs=read_access_specs)
        request.pduDestination = Address('192.168.2.70')
        if _debug:
            ReadPointListApplication._debug('    - request: %r', request)
        # make an IOCB
        iocb = IOCB(request)
        # set a callback for the response
        iocb.add_callback(self.complete_multi_request)
        if _debug:
            ReadPointListApplication._debug("    - iocb: %r", iocb)
        # send the request
        self.request_io(iocb)

    def complete_multi_request(self, iocb):
        if _debug:
            ReadPointListApplication._debug("complete_request %r", iocb)
        if iocb.ioResponse:
            apdu = iocb.ioResponse
            # loop through the results
            for result in apdu.listOfReadAccessResults:
                # here is the object identifier
                object_identifier = result.objectIdentifier
                self.response_values[object_identifier] = {}
                if _debug:
                    ReadPointListApplication._debug("    - objectIdentifier: %r", object_identifier)
                # now come the property values per object
                for element in result.listOfResults:
                    # get the property and array index
                    property_identifier = element.propertyIdentifier
                    if _debug:
                        ReadPointListApplication._debug("    - propertyIdentifier: %r", property_identifier)
                    property_array_index = element.propertyArrayIndex
                    if _debug:
                        ReadPointListApplication._debug("    - propertyArrayIndex: %r", property_array_index)
                    # here is the read result
                    read_result = element.readResult
                    # check for an error
                    if read_result.propertyAccessError is not None:
                        self.response_values[object_identifier][property_identifier] = f'! {read_result.propertyAccessError}'
                    else:
                        # here is the value
                        property_value = read_result.propertyValue
                        # find the datatype
                        datatype = get_datatype(object_identifier[0], property_identifier)
                        if _debug:
                            ReadPointListApplication._debug("    - datatype: %r", datatype)
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
        if iocb.ioError:
            if _debug:
                ReadPointListApplication._debug("    - error: %r", iocb.ioError)
        stop()


def main():
    # make a device object
    this_device = LocalDeviceObject(
        objectName='Energy Box',
        objectIdentifier=599,
        maxApduLengthAccepted=1024,
        segmentationSupported='segmentedBoth',
        vendorIdentifier=15,
    )

    points = []
    for i in range(40):
        points.append(('analogInput', i, ['presentValue']))
    this_application = ReadPointListApplication(points, this_device, '192.168.2.109')

    # get the services supported
    services_supported = this_application.get_services_supported()
    if _debug:
        _log.debug("    - services_supported: %r", services_supported)

    # let the device object know
    this_device.protocolServicesSupported = services_supported.value
    deferred(this_application.do_device_request, 881000, '192.168.2.70')
    deferred(this_application.do_multi_request)
    _log.debug("running")
    run()

    # dump out the results
    pprint.pprint(this_application.device_properties)
    pprint.pprint(this_application.response_values)


if __name__ == "__main__":
    main()
