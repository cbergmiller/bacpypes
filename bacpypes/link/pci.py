
import logging
from ..comm import PCI as _PCI


DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['PCI']


class PCI(_PCI):
    """
    Link Layer Protocol-control information
    (from former pdu.py module)
    """
    _debug_contents = ('pduExpectingReply', 'pduNetworkPriority')

    def __init__(self, *args, **kwargs):
        if DEBUG: _logger.debug('PCI.__init__ %r %r', args, kwargs)
        # split out the keyword arguments that belong to this class
        my_kwargs = {}
        other_kwargs = {}
        for element in ('expectingReply', 'networkPriority'):
            if element in kwargs:
                my_kwargs[element] = kwargs[element]
        for kw in kwargs:
            if kw not in my_kwargs:
                other_kwargs[kw] = kwargs[kw]
        if DEBUG: _logger.debug('    - my_kwargs: %r', my_kwargs)
        if DEBUG: _logger.debug('    - other_kwargs: %r', other_kwargs)
        # call some superclass, if there is one
        super(PCI, self).__init__(*args, **other_kwargs)
        # set the attribute/property values for the ones provided
        self.pduExpectingReply = my_kwargs.get('expectingReply', 0)  # see 6.2.2 (1 or 0)
        self.pduNetworkPriority = my_kwargs.get('networkPriority', 0)  # see 6.2.2 (0..3)

    def update(self, pci):
        """Copy the PCI fields."""
        _PCI.update(self, pci)
        # now do the BACnet PCI fields
        self.pduExpectingReply = pci.pduExpectingReply
        self.pduNetworkPriority = pci.pduNetworkPriority

    def pci_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if DEBUG: _logger.debug('pci_contents use_dict=%r as_class=%r', use_dict, as_class)
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()
        # call the parent class
        _PCI.pci_contents(self, use_dict=use_dict, as_class=as_class)
        # save the values
        use_dict.__setitem__('expectingReply', self.pduExpectingReply)
        use_dict.__setitem__('networkPriority', self.pduNetworkPriority)
        # return what we built/updated
        return use_dict

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if DEBUG: _logger.debug(f'dict_contents use_dict=%r as_class=%r', use_dict, as_class)
        return self.pci_contents(use_dict=use_dict, as_class=as_class)
