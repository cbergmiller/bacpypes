
import logging

from .bindings import bind, element_map, service_map
from ..errors import ConfigurationError

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['ApplicationServiceElement', 'NullServiceElement', 'DebugServiceElement']


class ApplicationServiceElement:
    """
    ApplicationServiceElement
    """
    def __init__(self, aseID=None):
        if DEBUG: _logger.debug("__init__(%s)", aseID)

        self.elementID = aseID
        self.elementService = None
        if aseID is not None:
            if aseID in element_map:
                raise ConfigurationError(f'already an application service element {aseID!r}')
            element_map[aseID] = self
            # automatically bind
            if aseID in service_map:
                service = service_map[aseID]
                if service.serviceElement:
                    raise ConfigurationError(f'service access point {aseID!r} already bound')
                bind(self, service)

    def request(self, *args, **kwargs):
        if DEBUG: _logger.debug("request(%s) %r %r", self.elementID, args, kwargs)
        if not self.elementService:
            raise ConfigurationError('unbound application service element')
        self.elementService.sap_indication(*args, **kwargs)

    def indication(self, *args, **kwargs):
        raise NotImplementedError('indication must be overridden')

    def response(self, *args, **kwargs):
        if DEBUG: _logger.debug("response(%s) %r %r", self.elementID, args, kwargs)
        if not self.elementService:
            raise ConfigurationError('unbound application service element')
        self.elementService.sap_confirmation(*args, **kwargs)

    def confirmation(self, *args, **kwargs):
        raise NotImplementedError('confirmation must be overridden')


class NullServiceElement(ApplicationServiceElement):
    """
    NullServiceElement
    """
    def indication(self, *args, **kwargs):
        pass

    def confirmation(self, *args, **kwargs):
        pass


class DebugServiceElement(ApplicationServiceElement):
    """
    DebugServiceElement
    """
    def indication(self, *args, **kwargs):
        print(f'DebugServiceElement({self.elementID!s}).indication')
        print(f'    - args: {args!r}')
        print(f'    - kwargs: {kwargs!r}')

    def confirmation(self, *args, **kwargs):
        print(f'DebugServiceElement({self.elementID!s}).confirmation')
        print(f'    - args: {args!r}')
        print(f'    - kwargs: {kwargs!r}')
