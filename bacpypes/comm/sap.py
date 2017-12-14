
import logging

from .bindings import bind, service_map, element_map
from ..errors import ConfigurationError

DEBUG = False
_logger = logging.getLogger(__name__)

__all__ = ['ServiceAccessPoint']


class ServiceAccessPoint:
    """
    ServiceAccessPoint
    Note that the SAP functions have been renamed so a derived class
    can inherit from both Client, Service, and ServiceAccessPoint
    at the same time.
    """
    def __init__(self, sapID=None):
        if DEBUG: _logger.debug("__init__(%s)", sapID)
        self.serviceID = sapID
        self.serviceElement = None
        if sapID is not None:
            if sapID in service_map:
                raise ConfigurationError(f'already a service access point {sapID!r}')
            service_map[sapID] = self
            # automatically bind
            if sapID in element_map:
                element = element_map[sapID]
                if element.elementService:
                    raise ConfigurationError(f'application service element {sapID!r} already bound')
                bind(element, self)

    def sap_request(self, *args, **kwargs):
        if DEBUG: _logger.debug("sap_request(%s) %r %r", self.serviceID, args, kwargs)
        if not self.serviceElement:
            raise ConfigurationError('unbound service access point')
        self.serviceElement.indication(*args, **kwargs)

    def sap_indication(self, *args, **kwargs):
        raise NotImplementedError('sap_indication must be overridden')

    def sap_response(self, *args, **kwargs):
        if DEBUG: _logger.debug("sap_response(%s) %r %r", self.serviceID, args, kwargs)
        if not self.serviceElement:
            raise ConfigurationError('unbound service access point')
        self.serviceElement.confirmation(*args, **kwargs)

    def sap_confirmation(self, *args, **kwargs):
        raise NotImplementedError('sap_confirmation must be overridden')