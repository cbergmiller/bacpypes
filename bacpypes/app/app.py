#!/usr/bin/python

"""
Application Module
"""

import warnings
import logging
from ..comm import ApplicationServiceElement, Collector
from ..link import Address
from ..primitivedata import ObjectIdentifier
from ..apdu import UnconfirmedRequestPDU, ConfirmedRequestPDU, Error
from ..errors import ExecutionError, UnrecognizedService, AbortException, RejectException
# for computing protocol services supported
from ..apdu import confirmed_request_types, unconfirmed_request_types, \
    ConfirmedServiceChoice, UnconfirmedServiceChoice
from ..basetypes import ServicesSupported
from .deviceinfo import DeviceInfoCache

_logger = logging.getLogger(__name__)
__all__ = ['Application']


class Application(ApplicationServiceElement, Collector):
    """
    Application
    """
    def __init__(self, localDevice=None, localAddress=None, deviceInfoCache=None, aseID=None):
        ApplicationServiceElement.__init__(self, aseID)
        # local objects by ID and name
        self.objectName = {}
        self.objectIdentifier = {}
        # keep track of the local device
        if localDevice:
            self.localDevice = localDevice
            # bind the device object to this application
            localDevice._app = self
            # local objects by ID and name
            self.objectName[localDevice.objectName] = localDevice
            self.objectIdentifier[localDevice.objectIdentifier] = localDevice
        # local address deprecated, but continue to use the old initializer
        if localAddress is not None:
            warnings.warn('local address at the application layer deprecated', DeprecationWarning)
            # allow the address to be cast to the correct type
            if isinstance(localAddress, Address):
                self.localAddress = localAddress
            else:
                self.localAddress = Address(localAddress)
        # use the provided cache or make a default one
        self.deviceInfoCache = deviceInfoCache or DeviceInfoCache()
        # controllers for managing confirmed requests as a client
        self.controllers = {}
        # now set up the rest of the capabilities
        Collector.__init__(self)

    def add_object(self, obj):
        """Add an object to the local collection."""
        # extract the object name and identifier
        object_name = obj.objectName
        if not object_name:
            raise RuntimeError('object name required')
        object_identifier = obj.objectIdentifier
        if not object_identifier:
            raise RuntimeError('object identifier required')
        # assuming the object identifier is well formed, check the instance number
        if object_identifier[1] >= ObjectIdentifier.maximum_instance_number:
            raise RuntimeError('invalid object identifier')
        # make sure it hasn't already been defined
        if object_name in self.objectName:
            raise RuntimeError(f'already an object with name {object_name!r}')
        if object_identifier in self.objectIdentifier:
            raise RuntimeError(f'already an object with identifier {object_identifier!r}')
        # now put it in local dictionaries
        self.objectName[object_name] = obj
        self.objectIdentifier[object_identifier] = obj
        # append the new object's identifier to the local device's object list
        # if there is one and it has an object list property
        if self.localDevice and self.localDevice.objectList:
            self.localDevice.objectList.append(object_identifier)
        # let the object know which application stack it belongs to
        obj._app = self

    def delete_object(self, obj):
        """Add an object to the local collection."""
        # extract the object name and identifier
        object_name = obj.objectName
        object_identifier = obj.objectIdentifier
        # delete it from the application
        del self.objectName[object_name]
        del self.objectIdentifier[object_identifier]
        # remove the object's identifier from the device's object list
        # if there is one and it has an object list property
        if self.localDevice and self.localDevice.objectList:
            indx = self.localDevice.objectList.index(object_identifier)
            del self.localDevice.objectList[indx]
        # make sure the object knows it's detached from an application
        obj._app = None

    def get_object_id(self, objid):
        """Return a local object or None."""
        return self.objectIdentifier.get(objid, None)

    def get_object_name(self, objname):
        """Return a local object or None."""
        return self.objectName.get(objname, None)

    def iter_objects(self):
        """Iterate over the objects."""
        return iter(self.objectIdentifier.values())

    def get_services_supported(self):
        """
        Return a ServicesSupported bit string based in introspection,
        look for helper methods that match confirmed and unconfirmed services.
        """
        services_supported = ServicesSupported()
        # look through the confirmed services
        for service_choice, service_request_class in confirmed_request_types.items():
            service_helper = f'do_{service_request_class.__name__}' 
            if hasattr(self, service_helper):
                service_supported = ConfirmedServiceChoice._xlate_table[service_choice]
                services_supported[service_supported] = 1

        # look through the unconfirmed services
        for service_choice, service_request_class in unconfirmed_request_types.items():
            service_helper = f'do_{service_request_class.__name__}'
            if hasattr(self, service_helper):
                service_supported = UnconfirmedServiceChoice._xlate_table[service_choice]
                services_supported[service_supported] = 1

        # return the bit list
        return services_supported

    def request(self, apdu):
        # double check the input is the right kind of APDU
        if not isinstance(apdu, (UnconfirmedRequestPDU, ConfirmedRequestPDU)):
            raise TypeError('APDU expected')

        # continue
        super(Application, self).request(apdu)

    def indication(self, apdu):
        # get a helper function
        helper_name = f'do_{apdu.__class__.__name__}' 
        helper_fn = getattr(self, helper_name, None)
        # send back a reject for unrecognized services
        if not helper_fn:
            if isinstance(apdu, ConfirmedRequestPDU):
                raise UnrecognizedService(f'no function {helper_name}')
            return
        # pass the apdu on to the helper function
        try:
            helper_fn(apdu)
        except RejectException as err:
            raise
        except AbortException as err:
            raise
        except ExecutionError as err:
            # send back an error
            if isinstance(apdu, ConfirmedRequestPDU):
                resp = Error(errorClass=err.errorClass, errorCode=err.errorCode, context=apdu)
                self.response(resp)
        except Exception as err:
            _logger.exception("exception: %r", err)
            # send back an error
            if isinstance(apdu, ConfirmedRequestPDU):
                resp = Error(errorClass='device', errorCode='operationalProblem', context=apdu)
                self.response(resp)
