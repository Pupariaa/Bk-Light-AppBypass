#!/usr/bin/env python3
"""
Scan for BLE devices with names starting with 'LED_BLE' and report their addresses.
"""

import asyncio
from bleak import BleakScanner

SCAN_SECONDS = 8          # how long to scan for advertisements


async def main():
    print(f"Scanning for {SCAN_SECONDS}s...")
    devices = await BleakScanner.discover(timeout=SCAN_SECONDS)
    if not devices:
        print("No BLE devices found.")
        return

    # Filter devices by name starting with LED_BLE
    led_ble_devices = [d for d in devices if d.name and d.name.startswith("LED_BLE")]
    
    if not led_ble_devices:
        print("No devices with names starting with 'LED_BLE' found.")
        return

    print("\nDevices with names starting with 'LED_BLE':")
    for device in led_ble_devices:
        print(f"- {device.address}  name='{device.name or ''}'")


if __name__ == "__main__":
    asyncio.run(main())