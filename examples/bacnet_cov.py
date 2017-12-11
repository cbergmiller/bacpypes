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

from bacpypes.core import run, stop, deferred, enable_sleeping
from bacpypes.iocb import IOCB

from bacpypes.pdu import Address
from bacpypes.object import get_datatype

from bacpypes.apdu import ReadPropertyRequest, ReadPropertyMultipleRequest, ReadAccessSpecification, PropertyReference, SubscribeCOVRequest
from bacpypes.primitivedata import Unsigned
from bacpypes.constructeddata import Array

from bacpypes.app import BIPSimpleApplication
from bacpypes.service.device import LocalDeviceObject

# some debugging
_debug = 1
_log = ModuleLogger(globals())
ConsoleLogHandler(__name__)
# globals
this_application = None


@bacpypes_debugging
class ReadPointListApplication(BIPSimpleApplication):

    def __init__(self, points, *args):
        BIPSimpleApplication.__init__(self, *args)
        # turn the point list into a queue
        self.points = points
        # make a list of the response values
        self.response_values = {}

    def do_request(self):
        if _debug:
            ReadPointListApplication._debug('do_request')

        request = SubscribeCOVRequest(
            subscriberProcessIdentifier=1234,
            monitoredObjectIdentifier=('analogInput', 0),
            issueConfirmedNotifications=False,
            lifetime=100
        )
        request.pduDestination = Address('192.168.2.70')
        if _debug:
            ReadPointListApplication._debug('    - request: %r', request)
        # make an IOCB
        iocb = IOCB(request)
        # set a callback for the response
        # iocb.add_callback(self.complete_request)
        if _debug:
            ReadPointListApplication._debug("    - iocb: %r", iocb)
        # send the request
        this_application.request_io(iocb)
        iocb.wait()
        # do something for success
        if iocb.ioResponse:
            if _debug: ReadPointListApplication._debug("    - response: %r", iocb.ioResponse)

        # do something for error/reject/abort
        if iocb.ioError:
            if _debug: ReadPointListApplication._debug("    - error: %r", iocb.ioError)

    def do_UnconfirmedCOVNotificationRequest(self, apdu):
        if _debug: ReadPointListApplication._debug("do_UnconfirmedCOVNotificationRequest %r", apdu)

        print("{} changed\n    {}".format(
            apdu.monitoredObjectIdentifier,
            ",\n    ".join("{} is {}".format(
                element.propertyIdentifier,
                str(element.value),
            ) for element in apdu.listOfValues),
        ))

    def complete_request(self, iocb):
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
    global this_application

    # make a device object
    this_device = LocalDeviceObject(
        objectName='Energy Box',
        objectIdentifier=599,
        maxApduLengthAccepted=1024,
        segmentationSupported='segmentedBoth',
        vendorIdentifier=15,
    )

    points = []
    for i in range(10):
        points.append(('analogInput', i, ['presentValue', 'objectName', 'units']))
    this_application = ReadPointListApplication(points, this_device, '10.81.0.14')

    # get the services supported
    services_supported = this_application.get_services_supported()
    if _debug:
        _log.debug("    - services_supported: %r", services_supported)

    # let the device object know
    this_device.protocolServicesSupported = services_supported.value

    # fire off a request when the core has a chance
    deferred(this_application.do_request)
    _log.debug("running")
    # enable_sleeping()
    run()

    # dump out the results
    pprint.pprint(this_application.response_values)

    _log.debug("fini")


if __name__ == "__main__":
    main()
