
import logging
from .client import Client
from .server import Server

_logger = logging.getLogger(__name__)
__all__ = ['Echo']


class Echo(Client, Server):
    """
    Echo
    """
    def __init__(self, cid=None, sid=None):
        _logger.debug('__init__ cid=%r sid=%r', cid, sid)
        Client.__init__(self, cid)
        Server.__init__(self, sid)

    def confirmation(self, *args, **kwargs):
        _logger.debug('confirmation %r %r', args, kwargs)
        self.request(*args, **kwargs)

    def indication(self, *args, **kwargs):
        _logger.debug('indication %r %r', args, kwargs)
        self.response(*args, **kwargs)