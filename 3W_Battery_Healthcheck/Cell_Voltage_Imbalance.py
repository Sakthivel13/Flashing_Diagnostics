# -*- coding: utf-8 -*-
"""
Created on Wed Jul 16 11:49:20 2025

@author: A.Harshitha
"""

import can
from datetime import datetime
 
# CAN ID for Cellvoltage difference
CAN_ID = 0x28
 
def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None
 
def parse_Cell_Imbalance(data):
        # Convert hex to binary strings
        Convert_6_byte = format(data[6], '08b')  # 4E (byte 7)
        Convert_7_byte = format(data[7], '08b')  # 0C (byte 8)
 
        # Combine 4E with 0C to form 16 bits
        combined_bits = Convert_6_byte + Convert_7_byte 
        print(f"Combined 16-bit Binary: {combined_bits}")
 
        # Convert 16-bit binary to decimal
        result_dec = int(combined_bits, 2)
        voltage_imbalance = result_dec * 0.01
        return voltage_imbalance
 
def Cell_Voltage_Imbalance():
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
                value = parse_Cell_Imbalance(msg.data)
                cell_imbalance=round(float(value),1)
                if cell_imbalance is not None:
                    data_detected = True
                break
    except Exception as e:
        print(f"Error while reading CAN messages: {e}")
    finally:
        bus.shutdown()
        status = "Passed" if data_detected else "Failed"
        print("Test_Sequence: Cell_Voltage_Imbalance")
        print(f"Tx_Can_id: {can_id}")
        print(f"Rx Hex_ID: {received_data_hex}")
        print(f"Rx Dec_ID: {received_data_dec}")
        print(f"Cell Voltage Imbalance: {cell_imbalance if cell_imbalance is not None else 'Not detected'} V")
        print(f"Status: {status}")
        return data_detected, cell_imbalance
 
if __name__ == "__Cell_Voltage_Imbalance__":
    result = Cell_Voltage_Imbalance()