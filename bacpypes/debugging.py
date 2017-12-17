#!/usr/bin/python

"""
Debugging
"""

import sys
import re
import logging
import binascii
from io import StringIO

DEBUG = False
_logger = logging.getLogger(__name__)


def btox(data, sep=''):
    """Return the hex encoding of a blob (byte string)."""
    # translate the blob into hex
    hex_str = str(binascii.hexlify(data), 'ascii')
    # inject the separator if it was given
    if sep:
        hex_str = sep.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
    # return the result
    return hex_str


def xtob(data, sep=''):
    """Interpret the hex encoding of a blob (byte string)."""
    # remove the non-hex characters
    data = re.sub("[^0-9a-fA-F]", '', data)
    # interpret the hex
    return binascii.unhexlify(data)


def ModuleLogger(globs):
    """Create a module level logger.

    To debug a module, create a _debug variable in the module, then use the
    ModuleLogger function to create a "module level" logger.  When a handler
    is added to this logger or a child of this logger, the _debug variable will
    be incremented.

    All of the calls within functions or class methods within the module should
    first check to see if _debug is set to prevent calls to formatter objects
    that aren't necessary.
    """
    # make sure that _debug is defined
    if '_debug' not in globs:
        raise RuntimeError("define _debug before creating a module logger")

    # create a logger to be assigned to _log
    logger = logging.getLogger(globs['__name__'])

    # put in a reference to the module globals
    logger.globs = globs

    return logger


class DebugContents(object):
    """
    DebugContents
    """
    def debug_contents(self, indent=1, stream=sys.stdout, _ids=None):
        """Debug the contents of an object."""
        classes = list(self.__class__.__mro__)
        classes.reverse()
        if DEBUG:
            _logger.debug("    - classes: %r", classes)
        # loop through the classes and look for _debug_contents
        attrs = []
        cids = []
        own_fn = []
        for cls in classes:
            if cls is DebugContents:
                continue
            if not issubclass(cls, DebugContents) and hasattr(cls, 'debug_contents'):
                for i, seenAlready in enumerate(own_fn):
                    if issubclass(cls, seenAlready):
                        del own_fn[i]
                        break
                own_fn.append(cls)
                continue
            # look for a tuple of attribute names
            debug_contents = getattr(cls, '_debug_contents', None)
            if not debug_contents:
                continue
            if not isinstance(debug_contents, tuple):
                raise ValueError(f'{cls.__name__}._debug_contents must be a tuple')
            if id(debug_contents) in cids:
                # already seen it
                continue
            cids.append(id(debug_contents))
            for attr in debug_contents:
                if attr not in attrs:
                    attrs.append(attr)
        if DEBUG:
            _logger.debug("    - attrs: %r", attrs)
            _logger.debug("    - own_fn: %r", own_fn)

        # make/extend the list of objects already seen
        if _ids is None:
            _ids = []
        # loop through the attributes
        for attr in attrs:
            # assume you're going deep, but not into lists and dicts
            go_deep = True
            go_list_dict = False
            go_hexed = False
            # attribute list might want to go deep
            if attr.endswith('-'):
                go_deep = False
                attr = attr[:-1]
            elif attr.endswith('*'):
                go_hexed = True
                attr = attr[:-1]
            elif attr.endswith('+'):
                go_deep = False
                go_list_dict = True
                attr = attr[:-1]
                if attr.endswith('+'):
                    go_deep = True
                    attr = attr[:-1]
            value = getattr(self, attr, None)
            # skip None
            if value is None:
                continue
            # standard output
            if go_list_dict and isinstance(value, list) and value:
                stream.write("%s%s = [\n" % ('    ' * indent, attr))
                indent += 1
                for i, elem in enumerate(value):
                    stream.write("%s[%d] %r\n" % ('    ' * indent, i, elem))
                    if go_deep and hasattr(elem, 'debug_contents'):
                        if id(elem) not in _ids:
                            _ids.append(id(elem))
                            elem.debug_contents(indent + 1, stream, _ids)
                indent -= 1
                stream.write("%s    ]\n" % ('    ' * indent,))
            elif go_list_dict and isinstance(value, dict) and value:
                stream.write("%s%s = {\n" % ('    ' * indent, attr))
                indent += 1
                for key, elem in value.items():
                    stream.write("%s%r : %r\n" % ('    ' * indent, key, elem))
                    if go_deep and hasattr(elem, 'debug_contents'):
                        if id(elem) not in _ids:
                            _ids.append(id(elem))
                            elem.debug_contents(indent + 1, stream, _ids)
                indent -= 1
                stream.write("%s    }\n" % ('    ' * indent,))
            elif go_hexed and isinstance(value, str):
                if len(value) > 20:
                    hexed = btox(value[:20], '.') + "..."
                else:
                    hexed = btox(value, '.')
                stream.write("%s%s = x'%s'\n" % ('    ' * indent, attr, hexed))
#           elif go_hexed and isinstance(value, int):
#               file.write("%s%s = 0x%X\n" % ('    ' * indent, attr, value))
            else:
                stream.write("%s%s = %r\n" % ('    ' * indent, attr, value))

                # go nested if it is debugable
                if go_deep and hasattr(value, 'debug_contents'):
                    if id(value) not in _ids:
                        _ids.append(id(value))
                        value.debug_contents(indent + 1, stream, _ids)

        # go through the functions
        own_fn.reverse()
        for cls in own_fn:
            cls.debug_contents(self, indent, stream, _ids)


class LoggingFormatter(logging.Formatter):
    """
    Custom logging formatter.
    """
    def format(self, record):
        try:
            # use the basic formatting
            msg = f'{logging.Formatter.format(self, record)}\n'
            # look for detailed arguments
            for arg in record.args:
                if isinstance(arg, DebugContents):
                    if msg:
                        sio = StringIO()
                        sio.write(msg)
                        msg = None
                    sio.write(f'    {arg!r}\n')
                    arg.debug_contents(indent=2, stream=sio)
            # get the message from the StringIO buffer
            if not msg:
                msg = sio.getvalue()
            # trim off the last '\n'
            msg = msg[:-1]
        except Exception as err:
            record_attrs = [
                f'{attr}: {getattr(record, attr, "N/A")}'
                for attr in ('name', 'level', 'pathname', 'lineno', 'msg', 'args', 'exc_info', 'func')
                ]
            record_attrs[:0] = [f'LoggingFormatter exception: {err}']
            msg = '\n    '.join(record_attrs)
        return msg

