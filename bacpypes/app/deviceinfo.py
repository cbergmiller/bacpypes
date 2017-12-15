
from ..debugging import DebugContents
from ..link import Address

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

    def __init__(self):
        # this information is from an IAmRequest
        self.deviceIdentifier = None                    # device identifier
        self.address = None                             # LocalStation or RemoteStation
        self.maxApduLengthAccepted = 1024               # maximum APDU device will accept
        self.segmentationSupported = 'noSegmentation'   # normally no segmentation
        self.vendorID = None                            # vendor identifier
        self.maxNpduLength = 1497           # maximum we can send in transit
        self.maxSegmentsAccepted = None     # value for proposed/actual window size


class DeviceInfoCache:
    """
    DeviceInfoCache
    """
    def __init__(self):
        self.cache = {}

    def has_device_info(self, key):
        """Return true if cache has information about the device."""
        return key in self.cache

    def add_device_info(self, apdu):
        """
        Create a device information record based on the contents of an IAmRequest and put it in the cache.
        """
        # get the existing cache record by identifier
        info = self.get_device_info(apdu.iAmDeviceIdentifier[1])
        # update existing record
        if info:
            if info.address == apdu.pduSource:
                return
            info.address = apdu.pduSource
        else:
            # get the existing record by address (creates a new record)
            info = self.get_device_info(apdu.pduSource)
            info.deviceIdentifier = apdu.iAmDeviceIdentifier[1]
        # update the rest of the values
        info.maxApduLengthAccepted = apdu.maxAPDULengthAccepted
        info.segmentationSupported = apdu.segmentationSupported
        info.vendorID = apdu.vendorID
        # say this is an updated record
        self.update_device_info(info)

    def get_device_info(self, key):
        """
        Return the known information about the device.  If the key is the address of an unknown device,
        build a generic device information record add put it in the cache.
        """
        if isinstance(key, int):
            current_info = self.cache.get(key, None)
        elif not isinstance(key, Address):
            raise TypeError('key must be integer or an address')
        elif key.addrType not in (Address.localStationAddr, Address.remoteStationAddr):
            raise TypeError('address must be a local or remote station')
        else:
            current_info = self.cache.get(key, None)
            if not current_info:
                current_info = DeviceInfo()
                current_info.address = key
                current_info._cache_keys = (None, key)
                current_info._ref_count = 1
                self.cache[key] = current_info
            else:
                current_info._ref_count += 1
        return current_info

    def update_device_info(self, info):
        """
        The application has updated one or more fields in the device information record
        and the cache needs to be updated to reflect the changes.
        If this is a cached version of a persistent record then this is the opportunity to update the database.
        """
        cache_id, cache_address = info._cache_keys

        if (cache_id is not None) and (info.deviceIdentifier != cache_id):
            # remove the old reference, add the new one
            del self.cache[cache_id]
            self.cache[info.deviceIdentifier] = info
            cache_id = info.deviceIdentifier
        if (cache_address is not None) and (info.address != cache_address):
            # remove the old reference, add the new one
            del self.cache[cache_address]
            self.cache[info.address] = info
            cache_address = info.address
        # update the keys
        info._cache_keys = (cache_id, cache_address)

    def release_device_info(self, info):
        """
        This function is called by the segmentation state machine when it has finished with the device information.
        """
        # this information record might be used by more than one SSM
        if info._ref_count > 1:
            info._ref_count -= 1
            return
        cache_id, cache_address = info._cache_keys
        if cache_id is not None:
            del self.cache[cache_id]
        if cache_address is not None:
            del self.cache[cache_address]
