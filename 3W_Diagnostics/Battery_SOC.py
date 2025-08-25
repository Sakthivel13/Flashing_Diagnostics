# -*- coding: utf-8 -*-
"""
Created on Thu Jun 26 14:57:04 2025

@author: Sri.Sakthivel
"""
import can
from datetime import datetime

# Battery SOC and Pack Voltage CAN ID (in hex)
BATTERY_SOC_CAN_ID = 0x775

def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None

def parse_battery_soc(data):
    try:
        # BMS_SOC: Byte [7] (1 byte, scaled by 0.4%)
        SOC = data[3] * 1
        return SOC
    except IndexError:
        return None, None

def Battery_SOC():
    bus = setup_can_bus()
    if not bus:
        return False
    
    SOC = None
    received_data_hex = "None"
    received_data_dec = "None"
    can_id = "None"
    data_detected = False

    try:
        start_time = datetime.now()
        while (datetime.now() - start_time).seconds < 1:
            msg = bus.recv(timeout=0.1)
            if msg and msg.arbitration_id == BATTERY_SOC_CAN_ID:
                can_id = hex(msg.arbitration_id)
                received_data_hex = ' '.join(f"{byte:02X}" for byte in msg.data)
                received_data_dec = ' '.join(str(byte) for byte in msg.data)
                SOC = parse_battery_soc(msg.data)
                if SOC is not None:
                    data_detected = True
                break
    except Exception as e:
        print(f"Error while reading CAN messages: {e}")
    finally:
        bus.shutdown()
        status = "Passed" if data_detected else "Failed"
        print("Test_Sequence: Battery SOC")
        print(f"Tx_Can_id: {can_id}")
        print(f"Rx Hex_ID: {received_data_hex}")
        print(f"Rx Dec_ID: {received_data_dec}")
        print(f"BMS SOC: {SOC if SOC is not None else 'Not detected'} %")
        print(f"Status: {status}")
        return data_detected, SOC

if __name__ == "__Battery_SOC__":
    result = Battery_SOC()