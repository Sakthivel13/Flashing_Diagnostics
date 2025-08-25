# -*- coding: utf-8 -*-
"""
Created on Mon Jun  9 11:54:00 2025
@author: Sri.Sakthivel
"""
import can
import requests
from datetime import datetime

PHASE_OFFSET_ANGLE_CAN_ID = 0xAB

def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None

def fetch_api_data(vin_number):
    url = f"http://10.121.2.107:3000/vehicles/flashFile/ejo/{vin_number}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        api_response = response.json()
        for module in api_response.get("data", {}).get("modules", []):
            if module.get("module") == "MCU":
                for config in module.get("configs", []):
                    if config.get("refname") == "MCU_PHASE_ANGLE_WRITE":
                        return api_response, float(config["messages"][0]["txbytes"]), True
        print("Phase Offset Angle not found in MCU module.")
        return api_response, None, False
    except Exception as e:
        print(f"API error: {e}")
        return None, None, False

def parse_phase_offset_angle(data):
    try:
        combined = (data[0] << 8) | data[1]
        if combined & 0x8000:
            combined = combined - 0x10000
        return round(float(combined) / 100, 2)  # Convert to float with 2 decimals
    except Exception:
        return None

def MCU_Phase_Offset(vin_number="MD6EVM1D7S4F00373"):
    bus = setup_can_bus()
    if not bus:
        return False

    api_response, api_phase_offset, success = fetch_api_data(vin_number)
    if not success:
        bus.shutdown()
        return False

    try:
        msg = can.Message(arbitration_id=PHASE_OFFSET_ANGLE_CAN_ID, data=[0xAA], is_extended_id=False)
        bus.send(msg)
        
        start_time = datetime.now()
        while (datetime.now() - start_time).seconds < 1:
            response = bus.recv(timeout=1)
            if response and response.arbitration_id == PHASE_OFFSET_ANGLE_CAN_ID:
                vehicle_offset = parse_phase_offset_angle(response.data)
                rx_hex = ' '.join(f"{byte:02X}" for byte in response.data)
                # Convert to string without decimal places for comparison
                vehicle_offset_str = int(vehicle_offset)
                api_phase_offset_str = int(api_phase_offset)
                match = (vehicle_offset_str == api_phase_offset_str)
                
                print("ECU Name: MCU")
                print(f"Tx_Can_id: {hex(response.arbitration_id)}")
                print(f"Rx Hex: {rx_hex}")
                print(f"Vehicle Phase Offset Angle: {vehicle_offset}")
                print(f"API Phase Offset Angle: {api_phase_offset}")
                print(f"Status: {'Passed' if match else 'Failed'}")
                
                return match, api_phase_offset, vehicle_offset
    except Exception as e:
        print(f"CAN read error: {e}")
    finally:
        bus.shutdown()

    print("No valid CAN response received.")
    return False

if __name__ == "__MCU_Phase_Offset__":
    MCU_Phase_Offset()