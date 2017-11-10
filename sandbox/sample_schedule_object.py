#!/usr/bin/env python

"""
Sample Schedule Object
"""

from functools import partial

from bacpypes.debugging import bacpypes_debugging, ModuleLogger
from bacpypes.consolelogging import ArgumentParser

from bacpypes.core import run_once
from bacpypes.task import RecurringTask

from bacpypes.primitivedata import Null, Integer, Real
from bacpypes.constructeddata import ArrayOf, AnyAtomic
from bacpypes.basetypes import DailySchedule, TimeValue
from bacpypes.object import register_object_type, WritableProperty, ScheduleObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
@register_object_type(vendor_id=999)
class SampleScheduleObject(ScheduleObject):

    properties = [
        WritableProperty('presentValue', AnyAtomic),
        ]

    def __init__(self, **kwargs):
        if _debug: SampleScheduleObject._debug("__init__ %r", kwargs)
        ScheduleObject.__init__(self, **kwargs)

        self._task = SampleScheduleInterpreter(self)


@bacpypes_debugging
class SampleScheduleInterpreter(RecurringTask):

    def __init__(self, sched_obj):
        if _debug: SampleScheduleInterpreter._debug("__init__ %r", sched_obj)
        RecurringTask.__init__(self, interval=1)

        # reference the schedule object to update
        self.sched_obj = sched_obj

    def process_task(self):
        if _debug: SampleScheduleInterpreter._debug("process_task")

#
#   something_changed
#

def something_changed(thing, old_value, new_value):
    print("%r changed from %r to %r" % (thing, old_value, new_value))

#
#
#

# parse the command line arguments
parser = ArgumentParser(usage=__doc__)
args = parser.parse_args()

if _debug: _log.debug("initialization")
if _debug: _log.debug("    - args: %r", args)

# make a schedule object with an integer value
so1 = SampleScheduleObject(
    objectIdentifier=1, objectName='Schedule 1 (integer)',
    presentValue=Integer(8),
    weeklySchedule=ArrayOf(DailySchedule)([
        DailySchedule(
            daySchedule=[
                TimeValue(time=(8,0,0,0), value=Integer(8)),
                TimeValue(time=(14,0,0,0), value=Null()),
                TimeValue(time=(17,0,0,0), value=Integer(42)),
                TimeValue(time=(0,0,0,0), value=Null()),
                ]),
        ] * 7),
    scheduleDefault=Integer(0),
    )
_log.debug("    - so1: %r", so1)

so2 = SampleScheduleObject(
    objectIdentifier=2, objectName='Schedule 2 (real)',
    presentValue=Real(73.5),
    weeklySchedule=ArrayOf(DailySchedule)([
        DailySchedule(
            daySchedule=[
                TimeValue(time=(9,0,0,0), value=Real(78.0)),
                TimeValue(time=(10,0,0,0), value=Null()),
                ]),
        ] * 7),
    scheduleDefault=Real(72.0),
    )
_log.debug("    - so2: %r", so2)

# add very simple monitors
so1._property_monitors['presentValue'].append(
    partial(something_changed, "so1"),
    )
so2._property_monitors['presentValue'].append(
    partial(something_changed, "so2"),
    )

# test it
so1.presentValue = Integer(1)

# change the element
so2.WriteProperty('presentValue', AnyAtomic(Real(80.0)))


