
import logging

from ..debugging import DebugContents
from .iocb import IOCB
from .iocb_states import *

_logger = logging.getLogger(__name__)
__all__ = ['IOGroup']


class IOGroup(IOCB, DebugContents):
    """
    An `IOGroup` is like a set that is an IOCB.  The group will complete
    when all of the IOCBs that have been added to the group are complete.
    """
    _debug_contents = ('ioMembers',)

    def __init__(self):
        """Initialize a group."""
        _logger.debug('__init__')
        IOCB.__init__(self)
        # start with an empty list of members
        self.ioMembers = []
        # start out being done.  When an IOCB is added to the
        # group that is not already completed, this state will
        # change to PENDING.
        self.io_state = COMPLETED
        self.io_complete.set()

    def add(self, iocb: IOCB):
        """
        Add an IOCB to the group, you can also add other groups.
        :param iocb: an IOCB to include in the group
        """
        _logger.debug('add %r', iocb)
        # add this to our members
        self.ioMembers.append(iocb)
        # assume all of our members have not completed yet
        self.io_state = PENDING
        self.io_complete.clear()
        # when this completes, call back to the group.  If this
        # has already completed, it will trigger
        iocb.add_callback(self.group_callback)

    def group_callback(self, iocb: IOCB):
        """
        This method is added as a callback to all of the IOCBs that are added
        to the group and it is called when each one completes.  Its purpose
        is to check to see if all of the IOCBs have completed and if they
        have, trigger the group as completed.
        : param iocb: the member IOCB that has completed
        """
        _logger.debug('group_callback %r', iocb)
        # check all the members
        for iocb in self.ioMembers:
            if not iocb.io_complete.isSet():
                _logger.debug('    - waiting for child: %r', iocb)
                break
        else:
            _logger.debug('    - all children complete')
            # everything complete
            self.io_state = COMPLETED
            self.trigger()

    def abort(self, err: Exception):
        """Called by a client to abort all of the member transactions.
        When the last pending member is aborted the group callback
        function will be called."""
        _logger.debug('abort %r', err)
        # change the state to reflect that it was killed
        self.io_state = ABORTED
        self.io_error = err
        # abort all the members
        for iocb in self.ioMembers:
            iocb.abort(err)
        # notify the client
        self.trigger()
