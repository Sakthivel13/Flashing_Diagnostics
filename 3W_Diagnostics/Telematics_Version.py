# -*- coding: utf-8 -*-
"""
Created on Fri May 30 08:19:00 2025

@author: Sri.Sakthivel
"""

import can
import time

# Telematics Software Version CAN ID (in hex, placeholder)
TELEMATICS_VERSION_CAN_ID = 0x702

def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None

def parse_telematics_version(data):
    try:
        # Major: Byte 4 (index 3), Micro: Byte 5 (index 4), Minor: Byte 6 (index 5)
        major = data[4]  # Byte 4
        micro = data[5]  # Byte 5
        minor = data[6]  # Byte 6
        version = f"{major}.{micro}.{minor}"
        return version
    except IndexError:
        return None

def Telematics_Version():
    bus = setup_can_bus()
    if not bus:
        return False
    
    version = None
    received_data_hex = "None"
    received_data_dec = "None"
    can_id = "None"
    version_detected = False

    try:
        start_time = time.time()
        while (time.time() - start_time) < 1:
            response = bus.recv(timeout=1)
            if response and response.arbitration_id == TELEMATICS_VERSION_CAN_ID:
                can_id = hex(response.arbitration_id)
                received_data_hex = ' '.join(f"{byte:02X}" for byte in response.data)
                received_data_dec = ' '.join(str(byte) for byte in response.data)
                version = parse_telematics_version(response.data)
                if version is not None:
                    version_detected = True
                break
    except Exception as e:
        print(f"Error while reading CAN messages: {e}")
    finally:
        bus.shutdown()
        status = "Passed" if version_detected else "Failed"
        print("ECU Name: Telematics ECU")
        print(f"Tx_Can_id: {can_id}")
        print(f"Rx Hex: {received_data_hex}")
        print(f"Rx Dec: {received_data_dec}")
        print(f"Telematics Version: {version}" )
        print(f"Status: {status}")
        return version_detected, version

if __name__ == "__Telematics_Version__":
    result = Telematics_Version()