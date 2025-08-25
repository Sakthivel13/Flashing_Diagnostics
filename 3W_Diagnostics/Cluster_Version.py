# -*- coding: utf-8 -*-
"""
Created on Fri May 30 14:48:00 2025

@author: Sri.Sakthivel
"""

import can
import time

# Cluster Firmware Version CAN ID (in hex)
CLUSTER_FW_ID = 0x77C

def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None

def parse_version(data):
    try:
        dec_data = [str(byte) for byte in data[3:6]]
        return f"{'.'.join(dec_data)}"
    except IndexError:
        return "Invalid data length"

def Cluster_Version():
    bus = setup_can_bus()
    if not bus:
        return False, None
    
    version = None
    received_data_hex = "None"
    received_data_dec = "None"
    can_id = "None"
    version_detected = False

    try:
        start_time = time.time()
        while (time.time() - start_time) < 1:
            response = bus.recv(timeout=1)
            if response and response.arbitration_id == CLUSTER_FW_ID:
                can_id = hex(response.arbitration_id)
                received_data_hex = ' '.join(f"{byte:02X}" for byte in response.data)
                received_data_dec = ' '.join(str(byte) for byte in response.data)
                version = parse_version(response.data)
                if version != "Invalid data length":
                    version_detected = True
                break
    except Exception as e:
        print(f"Error while reading CAN messages: {e}")
    finally:
        bus.shutdown()
        status = "Passed" if version_detected else "Failed"
        print("ECU Name: Cluster ECU")
        print(f"Tx_Can_id: {can_id}")
        print(f"Rx Hex: {received_data_hex}")
        print(f"Rx Dec: {received_data_dec}")
        print(f"Cluster Version: {version}")
        print(f"Status: {status}")
        return version_detected, version

if __name__ == "__Cluster_Version__":
    success, version = Cluster_Version()