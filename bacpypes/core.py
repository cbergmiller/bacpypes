#!/usr/bin/python

"""
Core
"""

import sys
import asyncore
import asyncio
import signal
import threading
import time
import traceback
import warnings
import logging
import functools

from .debugging import bacpypes_debugging, ModuleLogger

# some debugging
_debug = 0
_logger = logging.getLogger(__name__)

# globals
running = False
taskManager = None
deferredFns = []
sleeptime = 0.0


def stop(*args):
    """Call to stop running, may be called with a signum and frame
    parameter if called as a signal handler."""
    _logger.debug('stop')
    global running, taskManager
    if args:
        sys.stderr.write("===== TERM Signal, %s\n" % time.strftime("%d-%b-%Y %H:%M:%S"))
        sys.stderr.flush()
    running = False
    # trigger the task manager event
    if taskManager and taskManager.trigger:
        if _debug: stop._debug("    - trigger")
        taskManager.trigger.set()


def dump_stack():
    _logger.debug('dump_stack')
    for filename, lineno, fn, _ in traceback.extract_stack()[:-1]:
        sys.stderr.write("    %-20s  %s:%s\n" % (fn, filename.split('/')[-1], lineno))


def print_stack(sig, frame):
    """Signal handler to print a stack trace and some interesting values."""
    _logger.debug("print_stack %r %r", sig, frame)
    global running, deferredFns, sleeptime
    sys.stderr.write("==== USR1 Signal, %s\n" % time.strftime("%d-%b-%Y %H:%M:%S"))
    sys.stderr.write("---------- globals\n")
    sys.stderr.write("    running: %r\n" % (running,))
    sys.stderr.write("    deferredFns: %r\n" % (deferredFns,))
    sys.stderr.write("    sleeptime: %r\n" % (sleeptime,))
    sys.stderr.write("---------- stack\n")
    traceback.print_stack(frame)
    # make a list of interesting frames
    flist = []
    f = frame
    while f.f_back:
        flist.append(f)
        f = f.f_back
    # reverse the list so it is in the same order as print_stack
    flist.reverse()
    for f in flist:
        sys.stderr.write("---------- frame: %s\n" % (f,))
        for k, v in f.f_locals.items():
            sys.stderr.write("    %s: %r\n" % (k, v))
    sys.stderr.flush()


SPIN = 1.0


def run(spin=SPIN, sigterm=stop, sigusr1=print_stack):
    _logger.debug("run spin=%r sigterm=%r, sigusr1=%r", spin, sigterm, sigusr1)
    global running, taskManager, deferredFns, sleeptime

    # install the signal handlers if they have been provided (issue #112)
    if isinstance(threading.current_thread(), threading._MainThread):
        if (sigterm is not None) and hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, sigterm)
        if (sigusr1 is not None) and hasattr(signal, 'SIGUSR1'):
            signal.signal(signal.SIGUSR1, sigusr1)
    elif sigterm or sigusr1:
        warnings.warn("no signal handlers for child threads")
    # reference the task manager (a singleton)
    taskManager = TaskManager()
    # count how many times we are going through the loop
    loopCount = 0
    running = True
    while running:
        # if _debug: run._debug("    - time: %r", time.time())
        loopCount += 1
        # get the next task
        task, delta = taskManager.get_next_task()
        try:
            # if there is a task to process, do it
            if task:
                # if _debug: run._debug("    - task: %r", task)
                taskManager.process_task(task)
            # if delta is None, there are no tasks, default to spinning
            if delta is None:
                delta = spin
            # there may be threads around, sleep for a bit
            if sleeptime and (delta > sleeptime):
                time.sleep(sleeptime)
                delta -= sleeptime
            # if there are deferred functions, use a small delta
            if deferredFns:
                delta = min(delta, 0.001)
            # if _debug: run._debug("    - delta: %r", delta)
            # loop for socket activity
            asyncore.loop(timeout=delta, count=1)
            # check for deferred functions
            while deferredFns:
                # get a reference to the list
                fnlist = deferredFns
                deferredFns = []
                # call the functions
                for fn, args, kwargs in fnlist:
                    # if _debug: run._debug("    - call: %r %r %r", fn, args, kwargs)
                    fn(*args, **kwargs)
                # done with this list
                del fnlist

        except KeyboardInterrupt:
            _logger.info("keyboard interrupt")
            running = False
        except Exception as err:
            _logger.exception("an error has occurred: %s", err)
    running = False


def run_once():
    """
    Make a pass through the scheduled tasks and deferred functions just
    like the run() function but without the asyncore call (so there is no
    socket IO actviity) and the timers.
    """
    _logger.debug("run_once")
    global taskManager, deferredFns
    # reference the task manager (a singleton)
    taskManager = TaskManager()
    try:
        delta = 0.0
        while delta == 0.0:
            # get the next task
            task, delta = taskManager.get_next_task()
            _logger.debug("    - task, delta: %r, %r", task, delta)
            # if there is a task to process, do it
            if task:
                taskManager.process_task(task)
            # check for deferred functions
            while deferredFns:
                # get a reference to the list
                fnlist = deferredFns
                deferredFns = []
                # call the functions
                for fn, args, kwargs in fnlist:
                    _logger.debug("    - call: %r %r %r", fn, args, kwargs)
                    fn(*args, **kwargs)
                # done with this list
                del fnlist
    except KeyboardInterrupt:
        _logger.info("keyboard interrupt")
    except Exception as err:
        _logger.exception("an error has occurred: %s", err)


def deferred(fn, *args, **kwargs):
    _logger.debug("deferred %r %r %r", fn, args, kwargs)
    loop = asyncio.get_event_loop()
    loop.call_soon(functools.partial(fn, *args, **kwargs))


@bacpypes_debugging
def enable_sleeping(stime=0.001):
    _logger.debug("enable_sleeping %r", stime)
    global sleeptime
    # set the sleep time
    sleeptime = stime
