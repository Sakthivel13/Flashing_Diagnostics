# -*- coding: utf-8 -*-
"""
Created on Tue Aug 19 16:43:32 2025

@author: Sri.Sakthivel
"""

import can
from can.message import Message
import os

def log_message(direction, msg):
    formatted_data = ' '.join(f'{byte:02X}' for byte in msg.data)
    print(f"{direction} ID: {msg.arbitration_id:03X}, DLC: {msg.dlc}, Data: {formatted_data}")
    
def can_config(interface="can0",bitrate=500000):
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate} ")

def setup_can_bus():
    try:
        can_config(interface="can0",bitrate=500000)
        bus = can.interface.Bus(interface='socketcan', channel='can0', bitrate=500000)
        #bus = can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000, fd=False)
        return bus
    except Exception as e:
        print(f"SocketCAN setup failed: {e}")
        
    print("No CAN interface found.")
    return None

def WRITE_TPMS_FRONT(front_mac_id):
    print("Test_Sequence: WRITE_TPMS_FRONT")
    bus = setup_can_bus()
    if not bus:
        return False

    try:
        # Format MAC: 'C06380910000' ➝ [0xC0, 0x63, 0x80, 0x91, 0x00, 0x00]
        mac_bytes = [int(front_mac_id[i:i+2], 16) for i in range(0, len(front_mac_id), 2)]
        full_payload = [0x01] + mac_bytes + [0x00]  # 8 bytes

        message = Message(arbitration_id=0x7F3, data=bytearray(full_payload), is_fd=False, is_extended_id=False)
        log_message("Tx", message)
        bus.send(message)

        bus.set_filters([{"can_id": 0x7F1, "can_mask": 0x7FF, "extended": False}])
        response = bus.recv(timeout=2)

        if response:
            log_message("Rx", response)
            print("Front MAC Write: PASSED")
            return True
        else:
            print("No response received for Front MAC Write.")
            return False

    except can.CanError as e:
        print("CAN Error:", e)
        return False

    finally:
        bus.shutdown()
        print("CAN bus shutdown.")

if __name__ == "__main__":
    WRITE_TPMS_FRONT('C06380910000')  # Example MAC ID
