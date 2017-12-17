
import logging

from .bindings import bind, server_map, client_map
from ..errors import DecodingError, ConfigurationError

DEBUG = False
_logger = logging.getLogger(__name__)
__all__ = ['Client']


class Client:
    """
    Client
    """
    def __init__(self, cid=None):
        if DEBUG: _logger.debug('__init__ cid=%r', cid)
        self.clientID = cid
        self.clientPeer = None
        if cid is not None:
            if cid in client_map:
                raise ConfigurationError(f'already a client {cid!r}')
            client_map[cid] = self
            # automatically bind
            if cid in server_map:
                server = server_map[cid]
                if server.serverPeer:
                    raise ConfigurationError(f'server {cid!r} already bound')
                bind(self, server)

    def request(self, *args, **kwargs):
        if DEBUG: _logger.debug('request %r %r', args, kwargs)
        if not self.clientPeer:
            raise ConfigurationError('unbound client')
        self.clientPeer.indication(*args, **kwargs)

    def confirmation(self, *args, **kwargs):
        raise NotImplementedError('confirmation must be overridden')