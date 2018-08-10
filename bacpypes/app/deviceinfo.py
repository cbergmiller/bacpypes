
"""
The device information objects and associated cache are used to assist with
the following:

* Device-address-binding, the close associate between the device identifier
  for a device and its network address
* Construction of confirmed services to determine if a device can accept
  segmented requests and/or responses and the maximum size of an APDU
* The vendor of the device to know what additional vendor specific objects,
  properties, and other datatypes are available
"""

from ..debugging import DebugContents
from ..link import Address
from ..apdu import IAmRequest

__all__ = ['DeviceInfo', 'DeviceInfoCache']


class DeviceInfo(DebugContents):
    """
    DeviceInfo
    """
    _debug_contents = (
        'deviceIdentifier',
        'address',
        'maxApduLengthAccepted',
        'segmentationSupported',
        'vendorID',
        'maxNpduLength',
        'maxSegmentsAccepted',
    )

    def __init__(self, device_identifier, address):
        # this information is from an IAmRequest
        self.deviceIdentifier = device_identifier       # device identifier
        self.address = address                          # LocalStation or RemoteStation
        self.maxApduLengthAccepted = 1024               # maximum APDU device will accept
        self.segmentationSupported = 'noSegmentation'   # normally no segmentation
        self.maxSegmentsAccepted = None                 # None if no segmentation
        self.vendorID = None                            # vendor identifier
        self.maxNpduLength = None                       # maximum we can send in transit


class DeviceInfoCache:
    """
    An instance of this class is used to manage the cache of device information
    on behalf of the application.  The information may come from interrogating
    the device as it presents itself on the network or from a database, or
    some combination of the two.

    The default implementation is to only use information from the network and
    provide some reasonable defaults when information isn't available.  The
    :class:`Application` is provided a reference to an instance of this class
    or a derived class, and multiple application instances may share a cache,
    if that's appropriate.
    """
    def __init__(self, device_info_class=DeviceInfo):
        # a little error checking
        if not issubclass(device_info_class, DeviceInfo):
            raise ValueError("not a DeviceInfo subclass: %r" % (device_info_class,))
        self.cache = {}
        # class for new records
        self.device_info_class = device_info_class

    def has_device_info(self, key):
        """Return true if cache has information about the device."""
        return key in self.cache

    def iam_device_info(self, apdu):
        """Create a device information record based on the contents of an
        IAmRequest and put it in the cache."""
        # make sure the apdu is an I-Am
        if not isinstance(apdu, IAmRequest):
            raise ValueError("not an IAmRequest: %r" % (apdu,))

        # get the device instance
        device_instance = apdu.iAmDeviceIdentifier[1]

        # get the existing cache record if it exists
        device_info = self.cache.get(device_instance, None)

        # maybe there is a record for this address
        if not device_info:
            device_info = self.cache.get(apdu.pduSource, None)

        # make a new one using the class provided
        if not device_info:
            device_info = self.device_info_class(device_instance, apdu.pduSource)

        # jam in the correct values
        device_info.deviceIdentifier = device_instance
        device_info.address = apdu.pduSource
        device_info.maxApduLengthAccepted = apdu.maxAPDULengthAccepted
        device_info.segmentationSupported = apdu.segmentationSupported
        device_info.vendorID = apdu.vendorID

        # tell the cache this is an updated record
        self.update_device_info(device_info)

    def get_device_info(self, key):
        # get the info if it's there
        device_info = self.cache.get(key, None)
        return device_info

    def update_device_info(self, device_info):
        """The application has updated one or more fields in the device
        information record and the cache needs to be updated to reflect the
        changes.  If this is a cached version of a persistent record then this
        is the opportunity to update the database."""
        # give this a reference count if it doesn't have one
        if not hasattr(device_info, '_ref_count'):
            device_info._ref_count = 0

        # get the current keys
        cache_id, cache_address = getattr(device_info, '_cache_keys', (None, None))

        if (cache_id is not None) and (device_info.deviceIdentifier != cache_id):
            # remove the old reference, add the new one
            del self.cache[cache_id]
            self.cache[device_info.deviceIdentifier] = device_info

        if (cache_address is not None) and (device_info.address != cache_address):
            # remove the old reference, add the new one
            del self.cache[cache_address]
            self.cache[device_info.address] = device_info

        # update the keys
        device_info._cache_keys = (device_info.deviceIdentifier, device_info.address)

    def acquire(self, key):
        """Return the known information about the device.  If the key is the
        address of an unknown device, build a generic device information record
        add put it in the cache."""
        if isinstance(key, int):
            device_info = self.cache.get(key, None)

        elif not isinstance(key, Address):
            raise TypeError("key must be integer or an address")

        elif key.addrType not in (Address.localStationAddr, Address.remoteStationAddr):
            raise TypeError("address must be a local or remote station")

        else:
            device_info = self.cache.get(key, None)

        if device_info:
            device_info._ref_count += 1

        return device_info

    def release(self, device_info):
        """This function is called by the segmentation state machine when it
        has finished with the device information."""
        # this information record might be used by more than one SSM
        if device_info._ref_count == 0:
            raise RuntimeError("reference count")

        # decrement the reference count
        device_info._ref_count -= 1
