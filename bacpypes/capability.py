#!/usr/bin/python

"""
Capability
"""
import logging
from .debugging import bacpypes_debugging, ModuleLogger

_logger = logging.getLogger(__name__)


class Capability(object):
    """
    Capability
    """
    _zindex = 99


class Collector(object):
    """
    Collector
    """

    def __init__(self):
        # gather the capbilities
        self.capabilities = self._search_capability(self.__class__)
        # give them a chance to init
        for cls in self.capabilities:
            if hasattr(cls, '__init__') and cls is not Collector:
                cls.__init__(self)

    def _search_capability(self, base):
        """
        Given a class, return a list of all of the derived classes that are themselves derived from Capability.
        """
        rslt = []
        for cls in base.__bases__:
            if issubclass(cls, Collector):
                map(rslt.append, self._search_capability(cls))
            elif issubclass(cls, Capability):
                rslt.append(cls)
        return rslt

    def capability_functions(self, fn):
        """
        This generator yields functions that match the requested capability sorted by z-index.
        """
        # build a list of functions to call
        fns = []
        for cls in self.capabilities:
            xfn = getattr(cls, fn, None)
            if xfn:
                fns.append((getattr(cls, '_zindex', None), xfn))

        # sort them by z-index
        fns.sort(key=lambda v: v[0])
        # now yield them in order
        for xindx, xfn in fns:
            yield xfn

    def add_capability(self, cls):
        """Add a capability to this object."""
        # the new type has everything the current one has plus this new one
        bases = (self.__class__, cls)
        # save this additional class
        self.capabilities.append(cls)
        # morph into a new type
        newtype = type(self.__class__.__name__ + '+' + cls.__name__, bases, {})
        self.__class__ = newtype
        # allow the new type to init
        if hasattr(cls, '__init__'):
            cls.__init__(self)


def compose_capability(base, *classes):
    """Create a new class starting with the base and adding capabilities."""
    # make sure the base is a Collector
    if not issubclass(base, Collector):
        raise TypeError('base must be a subclass of Collector')
    # make sure you only add capabilities
    for cls in classes:
        if not issubclass(cls, Capability):
            raise TypeError(f'{cls} is not a Capability subclass')
    # start with everything the base has and add the new ones
    bases = (base,) + classes
    # build a new name
    name = base.__name__
    for cls in classes:
        name += '+' + cls.__name__
    # return a new type
    return type(name, bases, {})


def add_capability(base, *classes):
    """
    Add capabilites to an existing base, all objects get the additional functionality,
    but don't get inited.  Use with great care!
    """
    # start out with a collector
    if not issubclass(base, Collector):
        raise TypeError('base must be a subclass of Collector')
    # make sure you only add capabilities
    for cls in classes:
        if not issubclass(cls, Capability):
            raise TypeError(f'{cls} is not a Capability subclass')
    base.__bases__ += classes
    for cls in classes:
        base.__name__ += '+' + cls.__name__
