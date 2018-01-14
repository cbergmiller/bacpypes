
import logging

from .bindings import bind, server_map, client_map
from ..errors import ConfigurationError

DEBUG = True
_logger = logging.getLogger(__name__)
__all__ = ['Server']


class Server:
    """
    Server
    """
    def __init__(self, sid=None):
        if DEBUG: _logger.debug('__init__ sid=%r', sid)
        self.serverID = sid
        self.serverPeer = None
        if sid is not None:
            if sid in server_map:
                raise RuntimeError(f'already a server {sid!r}')
            server_map[sid] = self
            # automatically bind
            if sid in client_map:
                client = client_map[sid]
                if client.clientPeer:
                    raise ConfigurationError(f'client {sid!r} already bound')
                bind(client, self)

    def indication(self, *args, **kwargs):
        raise NotImplementedError('indication must be overridden')

    def response(self, *args, **kwargs):
        if DEBUG: _logger.debug('response %r %r', args, kwargs)
        if not self.serverPeer:
            raise ConfigurationError('unbound server')
        self.serverPeer.confirmation(*args, **kwargs)