"""
Communications Module
"""

import logging

DEBUG = False
_logger = logging.getLogger(__name__)

# prevent short/long struct overflow
_short_mask = 0xFFFF
_long_mask = 0xFFFFFFFF


# maps of named clients and servers
client_map = {}
server_map = {}

# maps of named SAPs and ASEs
service_map = {}
element_map = {}

__all__ = ['bind']


def bind(*args):
    """bind a list of clients and servers together, top down."""
    if DEBUG: _logger.debug('bind %r', args)
    # generic bind is pairs of names
    if not args:
        # find unbound clients and bind them
        for cid, client in client_map.items():
            # skip those that are already bound
            if client.clientPeer:
                continue
            if cid not in server_map:
                raise RuntimeError(f'unmatched server {cid!r}')
            server = server_map[cid]
            if server.serverPeer:
                raise RuntimeError(f'server already bound {cid!r}')
            bind(client, server)
        # see if there are any unbound servers
        for sid, server in server_map.items():
            if server.serverPeer:
                continue
            if sid not in client_map:
                raise RuntimeError(f'unmatched client {sid!r}')
            else:
                raise RuntimeError(f'mystery unbound server {sid!r}')
        # find unbound application service elements and bind them
        for eid, element in element_map.items():
            # skip those that are already bound
            if element.elementService:
                continue
            if eid not in service_map:
                raise RuntimeError(f'unmatched element {cid!r}')
            service = service_map[eid]
            # ToDo: should'nt this be `service` rather than `server`
            if server.serverPeer:
                raise RuntimeError(f'service already bound {cid!r}')
            bind(element, service)
        # see if there are any unbound services
        for sid, service in service_map.items():
            if service.serviceElement:
                continue
            if sid not in element_map:
                raise RuntimeError(f'unmatched service {sid!r}')
            else:
                raise RuntimeError(f'mystery unbound service {sid!r}')
    # Hack to prevent cyclic import
    from .client import Client
    from .server import Server
    from .service_element import ApplicationServiceElement
    from .sap import ServiceAccessPoint
    # go through the argument pairs
    for i in range(len(args)-1):
        client = args[i]
        if DEBUG: _logger.debug('    - client: %r', client)
        server = args[i+1]
        if DEBUG: _logger.debug('    - server: %r', server)
        # make sure we're binding clients and servers
        if isinstance(client, Client) and isinstance(server, Server):
            client.clientPeer = server
            server.serverPeer = client
        # we could be binding application clients and servers
        elif isinstance(client, ApplicationServiceElement) and isinstance(server, ServiceAccessPoint):
            client.elementService = server
            server.serviceElement = client
        # error
        else:
            raise TypeError('bind() requires a client and server')
        if DEBUG: _logger.debug('    - bound')

