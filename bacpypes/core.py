#!/usr/bin/python

"""
Core
"""

import asyncio
import logging
import functools

_logger = logging.getLogger(__name__)


def deferred(fn, *args, **kwargs):
    _logger.debug("deferred %r %r %r", fn, args, kwargs)
    loop = asyncio.get_event_loop()
    loop.call_soon(functools.partial(fn, *args, **kwargs))

