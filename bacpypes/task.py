#!/usr/bin/python

"""
Task
"""

import time
import asyncio
import logging
import functools

DEBUG = True
_logger = logging.getLogger(__name__)


def call_later(delay, fn, *args, **kwargs) -> asyncio.Handle:
    """
    Call a function after a delay (in seconds).
    """
    loop = asyncio.get_event_loop()
    callback = functools.partial(fn, *args, **kwargs)
    handle = loop.call_later(delay, callback)
    return handle


def call_soon(fn, *args, **kwargs):
    """
    Call a function in the event loop.
    """
    loop = asyncio.get_event_loop()
    callback = functools.partial(fn, *args, **kwargs)
    loop.call_soon(callback)


class RecurringTask:
    """
    Cyclically scheduled task.
    """
    def __init__(self, interval=None, offset=None, func=None):
        self.timeout_handle = None
        self.interval = interval
        self.offset = offset
        self.func = func

    def start(self, interval=None, offset=None, func=None):
        if interval is not None:
            self.interval = interval
        if offset is not None:
            self.offset = offset
        if func is not None:
            self.func = func
        if self.interval is None:
            raise ValueError('Interval must not be None')
        if self.interval <= 0.0:
            raise ValueError('Interval must be greater than zero')
        if self.interval is None:
            raise ValueError('Callback function must not be None')
        self.schedule_next_timeout()

    def handle_timeout(self):
        self.schedule_next_timeout()
        self.func()

    def schedule_next_timeout(self):
        # get ready for the next interval plus a jitter
        now = time.time()
        # interval and offset are in milliseconds to be consistent
        interval = self.interval / 1000.0
        if self.offset:
            offset = self.offset / 1000.0
        else:
            offset = 0.0
        delay = interval - ((now - offset) % interval)
        _logger.debug(f'delay {delay}')
        loop = asyncio.get_event_loop()
        loop.call_later(delay, self.handle_timeout)
