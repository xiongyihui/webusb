Get WebUSB Work
==============

The repository contains some utils and notes for WinUSB and WebUSB.
On Windows, WebUSB depends on WinUSB. There are 2 ways to get a driver-less WinUSB:

1. use MS OS 1.0 descriptors
2. use MS OS 2.0 descriptors

You can read these descriptors using `webusb.py`

## Notes
+ WebUSB doesn't work on a USB composite device using MS OS 1.0 descriptors yet (tested on Windows 10 at 2020-02-14)
+ To use WinUSB with MS OS 2.0 descriptors, `bcdUSB` must be >= `0201`
+ You can also use Zadig to install a WinUSB driver for a USB device if you can not add these descriptors.

## Resources
+ https://developers.google.com/web/fundamentals/native-hardware/build-for-webusb/
+ https://wicg.github.io/webusb/#webusb-platform-capability-descriptor
+ [Microsoft OS 2.0 Descriptors Specification](https://docs.microsoft.com/en-us/windows-hardware/drivers/usbcon/microsoft-os-2-0-descriptors-specification)