# -*- coding: utf-8 -*-
"""
Created on Fri Jun 27 12:33:56 2025

@author: A.Harshitha
"""

import can
import time
from can import Message
import pandas as pd
import os

def load_dtc_map_from_excel(excel_path):
    if not os.path.exists(excel_path):
        print(f"[ERROR] Excel file not found: {excel_path}")
        return {}

    try:
        df = pd.read_excel(excel_path)
        dtc_map = pd.Series(df['Description'].values, index=df['DTC Code']).to_dict()
        print("[INFO] DTC map loaded from Excel.")
        return dtc_map
    except Exception as e:
        print(f"[ERROR] Failed to read Excel: {e}")
        return {}

TESTER_REQUEST_ID = 0x7E1
MCU_RESPONSE_ID = 0x7E9
BITRATE = 500000

def log_message(direction, msg):
    data_str = ' '.join(f'{byte:02X}' for byte in msg.data)
    print(f"{direction} {msg.arbitration_id:04X} {msg.dlc} {data_str}")

def send_and_receive_isotp(bus, request, response_id, expected_sid=None, timeout=2.0):
    """Send UDS request and manually handle ISO-TP response."""
    msg = Message(arbitration_id=TESTER_REQUEST_ID, data=bytearray(request), is_fd=False, is_extended_id=False)
    log_message("Tx", msg)
    bus.send(msg)

    start_time = time.time()
    full_response = []

    while time.time() - start_time < timeout:
        msg = bus.recv(timeout=0.5)
        if not msg or msg.arbitration_id != response_id:
            continue

        log_message("Rx", msg)
        pci_type = (msg.data[0] & 0xF0) >> 4

        if pci_type == 0x0:
            # Single Frame
            length = msg.data[0] & 0x0F
            full_response = msg.data[1:1 + length]
            break

        elif pci_type == 0x1:
            # First Frame
            total_length = ((msg.data[0] & 0x0F) << 8) + msg.data[1]
            print(f"[DEBUG] Total length expected: {total_length}")
            full_response = list(msg.data[2:])

            # Send Flow Control (FC) frame
            fc_frame = [0x30, 0x00, 0x00] + [0x00] * 5
            fc_msg = Message(arbitration_id=TESTER_REQUEST_ID, data=bytearray(fc_frame), is_fd=False, is_extended_id=False)
            time.sleep(0.05)
            log_message("Tx", fc_msg)
            bus.send(fc_msg)
            time.sleep(0.05)

            seq_number_expected = 1
            while len(full_response) < total_length:
                cf = bus.recv(timeout=2.0)
                if cf and cf.arbitration_id == response_id:
                    log_message("Rx", cf)
                    seq_number = cf.data[0] & 0x0F
                    print(f"[DEBUG] CF Seq#: {seq_number}")
                    if seq_number != seq_number_expected:
                        print(f"[ERROR] Sequence mismatch. Expected: {seq_number_expected}, Got: {seq_number}")
                        return None
                    full_response.extend(cf.data[1:])
                    print(f"[DEBUG] Current accumulated: {len(full_response)}")
                    seq_number_expected = (seq_number_expected + 1) % 16
                else:
                    print("[ERROR] Timeout or no consecutive frame received.")
                    return None

            full_response = full_response[:total_length]
            break

    if expected_sid is not None:
        if not full_response or full_response[0] != expected_sid:
            print("[ERROR] Expected SID not found.")
            return None

    return full_response

def MCU_Read_DTC():
    try:
        bus = can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=BITRATE)
        print("[INFO] CAN initialized")
        
        # Load DTC Map from Excel
        excel_path = "D:/Python/CodeBee App/dtc error code/MCU_DTC_Error_codes.xlsx"
        DTC_MAP = load_dtc_map_from_excel(excel_path)

        # Add CAN filter to only receive responses from MCU
        bus.set_filters([{"can_id": MCU_RESPONSE_ID, "can_mask": 0x7FF}])

        # Step 1: Enter Extended Diagnostic Session
        diag_session_request = [0x02, 0x10, 0x03, 0, 0, 0, 0, 0]
        if not send_and_receive_isotp(bus, diag_session_request, MCU_RESPONSE_ID, expected_sid=0x50):
            print("[ERROR] Failed to enter Extended Diagnostic session.")
            return False, [{"code": "N/A", "description": "Session Entry Failed"}]

        # Step 2: Request DTCs
        read_dtc_request = [0x03, 0x19, 0x02, 0x8F, 0, 0, 0, 0]
        response = send_and_receive_isotp(bus, read_dtc_request, MCU_RESPONSE_ID, expected_sid=0x59)

        if not response:
            print("[ERROR] No DTC response received.")
            return False, [{"code": "N/A", "description": "No DTC Response"}]

        # Step 3: Parse DTCs
        dtc_payload = response[2:]  # Skip SID and subfunction

        # Remove leading FF
        while dtc_payload and dtc_payload[0] == 0xFF:
            dtc_payload = dtc_payload[1:]

        if len(dtc_payload) < 4:
            print("[INFO] No valid DTCs found.")
            return True, []

        detected_dtcs = []

        for i in range(0, len(dtc_payload), 4):
            if i + 3 >= len(dtc_payload):
                break

            dtc_bytes = dtc_payload[i:i+4]

            if dtc_bytes[0] == 0xFF:
                continue

            type_code = (dtc_bytes[0] & 0xC0) >> 6
            prefix = ["P", "C", "B", "U"][type_code]

            code = (dtc_bytes[1] << 8) | dtc_bytes[2]
            dtc_code = f"{prefix}{code:04X}"
            description = DTC_MAP.get(dtc_code, "Unknown DTC")

            detected_dtcs.append({
                "code": dtc_code,
                "description": description
            })

        if detected_dtcs:
            print(f"[RESULT] DTCs detected: {detected_dtcs}")
            return False, detected_dtcs
        else:
            return True, []

    except can.CanError as e:
        print("CAN Error:", e)
        return False, [{"code": "N/A", "description": f"CAN Error: {e}"}]

    finally:
        bus.shutdown()
        print("[INFO] CAN shutdown complete.")

if __name__ == "__main__":
    MCU_Read_DTC()