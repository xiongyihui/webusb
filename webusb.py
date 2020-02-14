#!/usr/bin/env python3

import sys
import os
from ctypes import (c_uint8, c_char, c_char_p, c_uint16, c_void_p, c_uint32,
                    c_ubyte, pointer, POINTER, Structure,
                    sizeof, cast, byref, addressof)
import libusb as usb


def perr(fmt, *args):
    print(fmt.format(*args), file=sys.stderr, end="")


def err_exit(errcode):
    perr("   {}\n", usb.strerror(usb.error(errcode)))
    return -1


# Microsoft OS Descriptor
MS_OS_DESC_STRING_INDEX = 0xEE
MS_OS_DESC_STRING_LENGTH = 0x12
MS_OS_DESC_VENDOR_CODE_OFFSET = 0x10

ms_os_desc_string = (c_uint8 * 16)(
    MS_OS_DESC_STRING_LENGTH,
    usb.LIBUSB_DT_STRING,
    ord(b'M'), 0, ord(b'S'), 0, ord(b'F'), 0, ord(b'T'), 0,
    ord(b'1'), 0, ord(b'0'), 0, ord(b'0'), 0,
)

WEBUSB_PLATFORM_CAPABILITY_UUID = "{3408B638-09A9-47A0-8BFD-A0768815B665}"
MS_OS_20_PLATFORM_CAPABILITY_UUID = "{D8DD60DF-4589-4CC7-9CD2-659D9E648A9F}"


class PlatformCapabilityDescriptor(Structure):
    _fields_ = [
        ("bLength", c_uint8),
        ("bDescriptorType", c_uint8),
        ("bDevCapabilityType", c_uint8),
        ("bReserved", c_uint8),
        ("PlatformCapabilityUUID", (c_uint8 * 16)),
        ("bcdVersion", c_uint16),
    ]


class MSOS20PlatformCapabilityDescriptor(Structure):
    _fields_ = [
        ("bLength", c_uint8),
        ("bDescriptorType", c_uint8),
        ("bDevCapabilityType", c_uint8),
        ("bReserved", c_uint8),
        ("PlatformCapabilityUUID", (c_uint8 * 16)),
        ("dwWindowsVersion", c_uint32),
        ("wMSOSDescriptorSetTotalLength", c_uint16),
        ("bVendorCode", c_uint8),
        ("bAltEnumCode", c_uint8),
    ]


# https://wicg.github.io/webusb/#webusb-platform-capability-descriptor
class WebUSBPlatformCapabilityDescriptor(Structure):
    _fields_ = [
        ("bLength", c_uint8),
        ("bDescriptorType", c_uint8),
        ("bDevCapabilityType", c_uint8),
        ("bReserved", c_uint8),
        ("PlatformCapabilityUUID", (c_uint8 * 16)),
        ("bcdVersion", c_uint16),
        ("bVendorCode", c_uint8),
        ("iLandingPage", c_uint8),
    ]


def memcmp(a, b, size):
    a = cast(a, POINTER(c_uint8))
    b = cast(b, POINTER(c_uint8))
    for i in range(size):
        d = a[i] - b[i]
        if d:
            return d

    return 0


# static
# @annotate(buffer=unsigned char*, size=unsigned int)
def dump_hex(buffer, size):
    for i in range(0, size, 16):
        print("\n  {:08x}  ".format(i), end="")
        for j in range(16):
            if i + j < size:
                print("{:02X}".format(buffer[i + j]), end="")
            else:
                print("  ", end="")
            print(" ", end="")
        print(" ", end="")
        for j in range(16):
            if i + j < size:
                if buffer[i + j] < 32 or buffer[i + j] > 126:
                    print(".", end="")
                else:
                    print("{:c}".format(buffer[i + j]), end="")
    print("\n")


def uuid_to_string(uuid):
    return ("{{{:02X}{:02X}{:02X}{:02X}-{:02X}{:02X}-{:02X}{:02X}"
            "-{:02X}{:02X}-{:02X}{:02X}{:02X}{:02X}{:02X}{:02X}}}".format(
                uuid[3], uuid[2], uuid[1],  uuid[0],  uuid[5],  uuid[4],  uuid[7],  uuid[6],
                uuid[8], uuid[9], uuid[10], uuid[11], uuid[12], uuid[13], uuid[14], uuid[15]))


# Get bMS_VendorCode from the OS Descriptor
# 2 ways to get the os string descriptor
#   + use libusb.get_descriptor()
#   + use libusb.control_transfer()
def get_vendor_code_from_os_string_descriptor(handle):
    print("  Reading OS String Descriptor")
    # get its length from the descriptor header
    length = 4
    desc = (c_uint8 * length)()
    request_type = usb.LIBUSB_ENDPOINT_IN
    request = 0x06                  # GET_DESCRIPTOR (0x06)
    value = (0x03 << 8) | 0xEE      # STRING_DESCRIPTOR (0x03), INDEX (0xEE)
    index = 0x0000
    r = usb.control_transfer(handle,
                             request_type,
                             request,
                             value,
                             index,
                             desc,
                             length,
                             1000)
    if r == length:
        length = desc[0]
        desc = (c_uint8 * length)()

        # get the full descriptor
        r = usb.control_transfer(handle,
                                 request_type,
                                 request,
                                 value,
                                 index,
                                 desc,
                                 length,
                                 1000)
        if r == length:
            dump_hex(desc, r)
            return desc[MS_OS_DESC_VENDOR_CODE_OFFSET]

    # Another way
    # Read the OS String Descriptor at string index 0xEE
    desc = (c_uint8 * MS_OS_DESC_STRING_LENGTH)()
    r = usb.get_string_descriptor(handle, MS_OS_DESC_STRING_INDEX, 0,
                                  desc, MS_OS_DESC_STRING_LENGTH)

    if r == MS_OS_DESC_STRING_LENGTH and memcmp(ms_os_desc_string, desc, sizeof(ms_os_desc_string)) == 0:
        dump_hex(desc, r)
        return desc[MS_OS_DESC_VENDOR_CODE_OFFSET]


# Read MS OS 1.0 Descriptors
def read_ms_os_10_descriptors(handle):
    print("\nReading MS OS 1.0 Descriptors\n")

    vendor_code = get_vendor_code_from_os_string_descriptor(handle)
    if not vendor_code:
        print("    OS String Descriptor is not found")
        return

    print("  Reading Extended Compat ID OS Feature Descriptor")
    request_type = usb.LIBUSB_ENDPOINT_IN | usb.LIBUSB_REQUEST_TYPE_VENDOR | usb.LIBUSB_RECIPIENT_DEVICE
    request = vendor_code
    value = 0x0000
    index = 0x0004
    length = 8
    desc = (c_uint8 * length)()
    # Read the descriptor header
    r = usb.control_transfer(handle,
                             request_type,
                             request,
                             value,
                             index,
                             desc,
                             length,
                             1000)
    if r != length:
        print("    Extended Compat ID OS Feature Descriptor is not found")
        return

    length = cast(desc, POINTER(c_uint32))[0]  # c_uint32

    # Read the full feature descriptor
    desc = (c_uint8 * length)()
    r = usb.control_transfer(handle,
                             request_type,
                             request,
                             value,
                             index,
                             desc,
                             length,
                             1000)
    if r != length:
        print("    Extended Compat ID OS Feature Descriptor is not found")
        return

    dump_hex(desc, r)



# Read MS OS 2.0 Descriptors
def read_ms_os_20_descriptors(handle, vendor_code):
    print("\nReading MS OS 2.0 descriptors\n")

    print("  Reading MS OS 2.0 descriptor set header")
    request_type = usb.LIBUSB_ENDPOINT_IN | usb.LIBUSB_REQUEST_TYPE_VENDOR | usb.LIBUSB_RECIPIENT_DEVICE
    request = vendor_code
    value = 0x0000
    index = 0x0007
    length = 10
    desc = (c_uint8 * length)()
    # Read the descriptor header
    r = usb.control_transfer(handle,
                             request_type,
                             request,
                             value,
                             index,
                             desc,
                             length,
                             1000)
    if r != length:
        print("  Not found")
        return

    dump_hex(desc, r)

    length = cast(pointer(desc), POINTER(c_uint16))[4]

    # Read the full feature descriptor
    desc = (c_uint8 * length)()
    r = usb.control_transfer(handle,
                             request_type,
                             request,
                             value,
                             index,
                             desc,
                             length,
                             1000)
    if r != length:
        print("  Not found")
        return

    dump_hex(desc, r)


def print_device_cap(dev_cap):
    if dev_cap[0].bDevCapabilityType == usb.LIBUSB_BT_USB_2_0_EXTENSION:
        usb_2_0_ext = POINTER(usb.usb_2_0_extension_descriptor)()
        usb.get_usb_2_0_extension_descriptor(None, dev_cap, byref(usb_2_0_ext))
        if usb_2_0_ext:
            print("    USB 2.0 extension:")
            print("      attributes             : {:02X}".format(
                usb_2_0_ext[0].bmAttributes))
            usb.free_usb_2_0_extension_descriptor(usb_2_0_ext)

    elif dev_cap[0].bDevCapabilityType == usb.LIBUSB_BT_SS_USB_DEVICE_CAPABILITY:

        ss_usb_device_cap = POINTER(usb.ss_usb_device_capability_descriptor)()
        usb.get_ss_usb_device_capability_descriptor(
            None, dev_cap, byref(ss_usb_device_cap))
        if ss_usb_device_cap:
            print("    USB 3.0 capabilities:")
            print("      attributes             : {:02X}".format(
                ss_usb_device_cap[0].bmAttributes))
            print("      supported speeds       : {:04X}".format(
                ss_usb_device_cap[0].wSpeedSupported))
            print("      supported functionality: {:02X}".format(
                ss_usb_device_cap[0].bFunctionalitySupport))
            usb.free_ss_usb_device_capability_descriptor(ss_usb_device_cap)

    elif dev_cap[0].bDevCapabilityType == usb.LIBUSB_BT_CONTAINER_ID:
        container_id = POINTER(usb.container_id_descriptor)()
        usb.get_container_id_descriptor(None, dev_cap, byref(container_id))
        if container_id:
            print("    Container ID:\n      {}".format(
                uuid_to_string(container_id[0].ContainerID)))
            usb.free_container_id_descriptor(container_id)
    elif dev_cap[0].bDevCapabilityType == 0x05:
        print("    Platform Capability Descriptor")
    else:
        print("    Unknown BOS device capability {:02X}:".format(
            dev_cap[0].bDevCapabilityType))


def test_device(vid, pid):
    speed_name = [
        "Unknown",
        "1.5 Mbit/s (USB LowSpeed)",
        "12 Mbit/s (USB FullSpeed)",
        "480 Mbit/s (USB HighSpeed)",
        "5000 Mbit/s (USB SuperSpeed)",
    ]

    handle = usb.open_device_with_vid_pid(None, vid, pid)
    if not handle:
        perr("  Failed.\n")
        return -1

    try:
        dev = usb.get_device(handle)   # usb.device*
        bus = usb.get_bus_number(dev)  # c_uint8

        port_path = (c_uint8 * 8)()
        r = usb.get_port_numbers(dev, port_path, sizeof(port_path))
        if r > 0:
            print("\nDevice properties:")
            print("        bus number: {}".format(bus))
            print("         port path: {}".format(port_path[0]), end="")
            for i in range(1, r):
                print("->{}".format(port_path[i]), end="")
            print(" (from root hub)")
        r = usb.get_device_speed(dev)
        if r < 0 or r > 4:
            r = 0
        print("             speed: {}".format(speed_name[r]))

        print("\nReading device descriptor:")
        dev_desc = usb.device_descriptor()
        r = usb.get_device_descriptor(dev, byref(dev_desc))
        if r < 0:
            return err_exit(r)
        print("            length: {}".format(dev_desc.bLength))
        print("      device class: {}".format(dev_desc.bDeviceClass))
        print("           VID:PID: {:04X}:{:04X}".format(dev_desc.idVendor,
                                                         dev_desc.idProduct))
        print("         bcdDevice: {:04X}".format(dev_desc.bcdDevice))
        # Copy the string descriptors for easier parsing
        string_index = {}  # indexes of the string descriptors
        string_index["Manufacturer"] = dev_desc.iManufacturer
        string_index["Product"] = dev_desc.iProduct
        string_index["Serial Number"] = dev_desc.iSerialNumber

        print("\nReading string descriptors:")
        string = (c_uint8 * 128)()
        for key in string_index.keys():
            if string_index[key] == 0:
                continue
            r = usb.get_string_descriptor_ascii(handle, string_index[key],
                                                string, sizeof(string))
            if r > 0:
                print("   {}: {}".format(key, bytearray(string[:r]).decode()))

        # MS OS 1.0 Descriptors
        read_ms_os_10_descriptors(handle)

        print("\nReading BOS descriptor: ", end="")
        bos_desc = POINTER(usb.bos_descriptor)()
        if usb.get_bos_descriptor(handle, pointer(bos_desc)) == usb.LIBUSB_SUCCESS:
            print((bos_desc[0].bNumDeviceCaps))
            caps = cast(pointer(bos_desc[0].dev_capability), POINTER(
                POINTER(usb.bos_dev_capability_descriptor)))
            for i in range(bos_desc[0].bNumDeviceCaps):
                # print_device_cap(caps[i])
                if caps[i][0].bDevCapabilityType == 0x05:
                    desc = cast(caps[i], POINTER(
                        PlatformCapabilityDescriptor))[0]

                    uuid = uuid_to_string(desc.PlatformCapabilityUUID)

                    if uuid == MS_OS_20_PLATFORM_CAPABILITY_UUID:
                        print("  MS OS 2.0 Platform Capability Descriptor")
                        print("    UUID: {}".format(uuid))
                        desc = cast(caps[i], POINTER(
                            MSOS20PlatformCapabilityDescriptor))[0]
                        print("    VendorCode: 0x{:02X}".format(desc.bVendorCode))
                        read_ms_os_20_descriptors(handle, desc.bVendorCode)
                    elif uuid == WEBUSB_PLATFORM_CAPABILITY_UUID:
                        print("  WebUSB Platform Capability UUID")
                        print("    UUID: {}".format(uuid))
                        desc = cast(caps[i], POINTER(
                            WebUSBPlatformCapabilityDescriptor))[0]
                        print("    VendorCode: 0x{:02X}".format(desc.bVendorCode))
                    else:
                        print("    UUID: {}".format(uuid))


            usb.free_bos_descriptor(bos_desc)
        else:
            print("no descriptor")

    finally:
        usb.close(handle)

    return 0


def main():
    usage = 'Usage: python3 {} [-d] VID:PID'.format(sys.argv[0])
    argc = len(sys.argv)
    if 2 > argc or argc > 3:
        print(usage)
        sys.exit(1)
    if 3 == argc:
        if sys.argv[1] != '-d':
            print(usage)
            sys.exit(1)

        os.environ["LIBUSB_DEBUG"] = "4"  # usb.LIBUSB_LOG_LEVEL_DEBUG

    if sys.argv[-1].find(':') < 0:
        print('Invalid VID & PID')
        print(usage)
        sys.exit(1)

    ids = sys.argv[-1].split(':')
    vid = int(ids[0], 16)
    pid = int(ids[1], 16)

    version = usb.get_version()[0]
    print("Using libusb v{}.{}.{}.{}".format(
        version.major, version.minor, version.micro, version.nano))
    r = usb.init(None)
    if r < 0:
        sys.exit(r)

    try:
        usb.set_option(None, usb.LIBUSB_OPTION_LOG_LEVEL,
                       usb.LIBUSB_LOG_LEVEL_INFO)
        test_device(vid, pid)
    finally:
        usb.exit(None)


if __name__ == '__main__':
    main()
