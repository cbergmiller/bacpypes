#!/usr/bin/python

"""
Task
"""

import time
import math
import asyncio
import logging
import functools

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
    Cyclically scheduled function calls.
    """
    def __init__(self, interval=None, offset=None, func=None):
        self.timeout_handle = None
        self.interval = interval
        self.offset = offset
        self.func = func

    def start(self, interval=None, offset=None, func=None):
        """
        :param interval: Time between tasks in milliseconds
        :param offset: Offset (pos.) in milliseconds
        :param func: Function to call
        """
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
        loop = asyncio.get_event_loop()
        interval = self.interval / 1000
        when = interval * math.ceil(loop.time() / interval)
        if self.offset:
            when += self.offset / 1000
        loop.call_at(when, self.handle_timeout)
