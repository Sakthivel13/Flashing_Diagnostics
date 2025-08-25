# -*- coding: utf-8 -*-
"""
Created on Mon Jun 23 10:45:19 2025

@author: A.Harshitha
"""

import can
import time
from can import Message

# Define Clear DTC Request: 0x14 FF FF FF
clear_dtc_request = [0x04, 0x14, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00]
MAX_RETRIES = 1

def log_message(direction, msg):
    """Format and print CAN messages for request and positive response only."""
    formatted_data = ' '.join(f'{byte:02X}' for byte in msg.data)
    if (direction == "Tx" and msg.arbitration_id == 0x07E1) or \
       (direction == "Rx" and msg.arbitration_id == 0x07E9 and len(msg.data) > 1 and msg.data[1] == 0x54):
        print(f"{direction} {msg.arbitration_id:04X} {msg.dlc} {formatted_data}")
        
        
    #formatted_data = ' '.join(f'{byte:02X}' for byte in msg.data)
    #print(f"{direction} {msg.arbitration_id:04X} {msg.dlc} {formatted_data}")

def MCU_Clear_DTC():
    try:
        # Initialize CAN bus
        bus = can.interface.Bus(interface="pcan", channel="PCAN_USBBUS1", bitrate=500000, fd=False)
        print("CAN bus initialized.")

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\nAttempt {attempt} of {MAX_RETRIES}")
            
            # Send Clear DTC request
            message = Message(arbitration_id=0x7E1, data=bytearray(clear_dtc_request), is_fd=False, is_extended_id=False)
            log_message("Tx", message)
            bus.send(message)
            
            # Receive response
            start_time = time.time()
            while time.time() - start_time < 2.0:
                response = bus.recv(timeout=0.5)
                if response:
                    log_message("Rx", response)
                    
                    # Positive response: service ID should be 0x54
                    if response.arbitration_id == 0x7E9 and len(response.data) > 1:
                        if response.data[1] == 0x54:
                            print("Clear DTC: PASSED")
                            return True
                        else:
                            print(f"Unexpected response: {response.data[1]:02X}")
                            return False
            
            print("No valid response received, retrying...")
        
        print("Maximum retries reached. Clear DTC failed.")
        return False

    except can.CanError as e:
        print("CAN error:", e)

    finally:
        if 'bus' in locals() and bus is not None:
            bus.shutdown()
            print("CAN bus shutdown.")

if __name__ == "__main__":
    MCU_Clear_DTC()
