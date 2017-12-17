#!/usr/bin/python

"""
BACnet Streaming Link Layer Module
"""

import hashlib
import logging

_logger = logging.getLogger(__name__)
__all__ = ['bsl_pdu_types', 'register_bslpdu_type']

# a dictionary of message type values and classes
bsl_pdu_types = {}


def register_bslpdu_type(cls):
    bsl_pdu_types[cls.messageType] = cls


# Hash Functions
_md5 = lambda x: hashlib.md5(x).digest()
_sha1 = lambda x: hashlib.sha1(x).digest()
_sha224 = lambda x: hashlib.sha224(x).digest()
_sha256 = lambda x: hashlib.sha256(x).digest()
_sha384 = lambda x: hashlib.sha384(x).digest()
_sha512 = lambda x: hashlib.sha512(x).digest()

hash_functions = (_md5, _sha1, _sha224, _sha256, _sha384, _sha512)



