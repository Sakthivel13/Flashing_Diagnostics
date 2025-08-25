# -*- coding: utf-8 -*-
"""
Created on Wed Jul 16 14:09:22 2025

@author: A.Harshitha
"""

import can
from datetime import datetime

CAN_ID = 0x26

def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None

def parse_single_byte_data(data):
    byte_value = data[1]  # Extract the 1th byte (8 bits: bit 0 to 7)
    print(f"Raw Byte (hex): {format(byte_value, '02X')}, Binary: {format(byte_value, '08b')}")
    result = byte_value * 1  # Multiply with a factor of 1
    return result

def Min_Cell_Temp():
    bus = setup_can_bus()
    if not bus:
        return False, None

    result_value = None
    received_data_hex = "None"
    can_id = "None"
    data_detected = False

    try:
        start_time = datetime.now()
        while (datetime.now() - start_time).seconds < 1:
            msg = bus.recv(timeout=0.1)
            if msg and msg.arbitration_id == CAN_ID:
                can_id = hex(msg.arbitration_id)
                received_data_hex = ' '.join(f"{byte:02X}" for byte in msg.data)
                result_value = parse_single_byte_data(msg.data)
                Min_Cell_Temp=round(float(result_value),1)
                if Min_Cell_Temp is not None:
                    data_detected = True
                break
    except Exception as e:
        print(f"Error while reading CAN messages: {e}")
    finally:
        bus.shutdown()
        status = "Passed" if data_detected else "Failed"
        print("Test_Sequence: Min_Cell_Temp")
        print(f"Tx_Can_id: {can_id}")
        print(f"Rx Hex_ID: {received_data_hex}")
        print(f"Result Value: {Min_Cell_Temp if Min_Cell_Temp is not None else 'Not detected'}")
        print(f"Status: {status}")
        return data_detected, Min_Cell_Temp

if __name__ == "__Min_Cell_Temp__":
    Min_Cell_Temp()
