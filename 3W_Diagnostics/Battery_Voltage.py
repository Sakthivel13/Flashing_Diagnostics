# -*- coding: utf-8 -*-
"""
Created on Thu May 29 10:09:19 2025

@author: Sri.Sakthivel
"""

import can
from datetime import datetime
 
# CAN ID (example from previous context)
CAN_ID = 0x22
 
def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None
 
def parse_battery_voltage(data):
        # Convert hex to binary strings
        Convert_2_byte = format(data[2], '08b')  # 4E (byte 3)
        Convert_3_byte = format(data[3], '08b')  # 0C (byte 4)
 
        # Extract last two bits of 4E
        consider_last_2_bits = Convert_2_byte[-2:]  # e.g., '10' from '01001110'
 
        # Combine last two bits of 4E with 0C to form 10 bits
        combined_bits = consider_last_2_bits + Convert_3_byte  # e.g., '10' + '00001100' = '1000001100'
        print(f"Combined 10-bit Binary: {combined_bits}")
 
        # Convert 10-bit binary to decimal
        result_dec = int(combined_bits, 2)
        pack_voltage = result_dec * 0.1
        return pack_voltage
 
def Battery_Voltage():
    bus = setup_can_bus()
    if not bus:
        return False, None
 
    value = None
    received_data_hex = "None"
    received_data_dec = "None"
    can_id = "None"
    data_detected = False
 
    try:
        start_time = datetime.now()
        while (datetime.now() - start_time).seconds < 1:
            msg = bus.recv(timeout=0.1)
            if msg and msg.arbitration_id == CAN_ID:
                can_id = hex(msg.arbitration_id)
                received_data_hex = ' '.join(f"{byte:02X}" for byte in msg.data)
                received_data_dec = ' '.join(str(byte) for byte in msg.data)
                value = parse_battery_voltage(msg.data)
                battery_pack_voltage=round(float(value),1)
                if battery_pack_voltage is not None:
                    data_detected = True
                break
    except Exception as e:
        print(f"Error while reading CAN messages: {e}")
    finally:
        bus.shutdown()
        status = "Passed" if data_detected else "Failed"
        print("Test_Sequence: Battery_Voltage")
        print(f"Tx_Can_id: {can_id}")
        print(f"Rx Hex_ID: {received_data_hex}")
        print(f"Rx Dec_ID: {received_data_dec}")
        print(f"Battery Pack Voltage: {battery_pack_voltage if battery_pack_voltage is not None else 'Not detected'} V")
        print(f"Status: {status}")
        return data_detected, battery_pack_voltage
 
if __name__ == "__Battery_Voltage__":
    result = Battery_Voltage()