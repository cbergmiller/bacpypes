
import logging

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['PCI']


class PCI:
    """
    PCI
    """
    _debug_contents = ('pduUserData+', 'pduSource', 'pduDestination')

    def __init__(self, *args, **kwargs):
        if DEBUG: _logger.debug("__init__ %r %r", args, kwargs)
        # split out the keyword arguments that belong to this class
        my_kwargs = {}
        other_kwargs = {}
        for element in ('user_data', 'source', 'destination'):
            if element in kwargs:
                my_kwargs[element] = kwargs[element]
        for kw in kwargs:
            if kw not in my_kwargs:
                other_kwargs[kw] = kwargs[kw]
        if DEBUG: _logger.debug("    - my_kwargs: %r", my_kwargs)
        if DEBUG: _logger.debug("    - other_kwargs: %r", other_kwargs)
        # call some superclass, if there is one
        super(PCI, self).__init__(*args, **other_kwargs)
        # pick up some optional kwargs
        self.pduUserData = my_kwargs.get('user_data', None)
        self.pduSource = my_kwargs.get('source', None)
        self.pduDestination = my_kwargs.get('destination', None)

    def update(self, pci):
        """Copy the PCI fields."""
        self.pduUserData = pci.pduUserData
        self.pduSource = pci.pduSource
        self.pduDestination = pci.pduDestination

    def pci_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if DEBUG: _logger.debug("pci_contents use_dict=%r as_class=%r", use_dict, as_class)
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # save the values
        for k, v in (('user_data', self.pduUserData), ('source', self.pduSource), ('destination', self.pduDestination)):
            if DEBUG: _logger.debug("    - %r: %r", k, v)
            if v is None:
                continue
            if hasattr(v, 'dict_contents'):
                v = v.dict_contents(as_class=as_class)
            use_dict.__setitem__(k, v)
        # return what we built/updated
        return use_dict

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if DEBUG: _logger.debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)
        return self.pci_contents(use_dict=use_dict, as_class=as_class)