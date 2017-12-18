
# a dictionary of message type values and classes
apdu_types = {}
# a dictionary of confirmed request choices and classes
confirmed_request_types = {}
# a dictionary of complex ack choices and classes
complex_ack_types = {}
# a dictionary of unconfirmed request choices and classes
unconfirmed_request_types = {}
# a dictionary of unconfirmed request choices and classes
error_types = {}


def register_apdu_type(cls):
    apdu_types[cls.pduType] = cls
    return cls


def register_confirmed_request_type(cls):
    confirmed_request_types[cls.serviceChoice] = cls
    return cls


def register_complex_ack_type(cls):
    complex_ack_types[cls.serviceChoice] = cls
    return cls


def register_unconfirmed_request_type(cls):
    unconfirmed_request_types[cls.serviceChoice] = cls
    return cls


def register_error_type(cls):
    error_types[cls.serviceChoice] = cls
    return cls
