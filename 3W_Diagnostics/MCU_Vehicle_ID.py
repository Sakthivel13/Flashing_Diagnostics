# -*- coding: utf-8 -*-
"""
Created on Wed May 28 17:32:50 2025

@author: Sri.Sakthivel
"""
import can
import requests
from datetime import datetime

# MCU Vehicle ID CAN ID (in hex)
VEHICLE_ID_CAN_ID = 0xCB

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
        
        modules = api_response.get("data", {}).get("modules", [])
        vehicle_id = None
        
        for module in modules:
            if module.get("module") == "MCU":
                for config in module.get("configs", []):
                    if config.get("refname") == "VEHICLE_ID":
                        vehicle_id = config["messages"][0].get("txbytes")
                        #print(f"Vehicle_Id = {vehicle_id}")
        if vehicle_id is not None:
            return api_response, vehicle_id, True
        else:
            print("Vehicle ID not found in MCU module.")
            return api_response, None, False
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"Error occurred: {e}")
        return None, None, False

def parse_vehicle_id(data):
    try:
        # Combine first two bytes [0,1] into a 16-bit unsigned integer (big-endian)
        combined = (data[0] << 8) | data[1]
        return combined  # Decimal value
    except IndexError:
        return None

def MCU_Vehicle_ID(vin_number="MD6EVM1D7S4E01133"):
    bus = setup_can_bus()
    if not bus:
        return False
    
    # Fetch API data and ensure bus shutdown if API fails
    api_response, api_vehicle_id, success = fetch_api_data(vin_number)
    if not success:
        bus.shutdown()
        return False
    
    vehicle_id = None
    received_data_hex = "None"
    received_data_dec = "None"
    can_id = "None"

    try:
        msg = can.Message(arbitration_id=VEHICLE_ID_CAN_ID, data=[0xAA], is_extended_id=False)
        bus.send(msg)
        
        start_time = datetime.now()
        while (datetime.now() - start_time).seconds < 1:
            response = bus.recv(timeout=1)
            if response and response.arbitration_id == VEHICLE_ID_CAN_ID:
                can_id = hex(response.arbitration_id)
                received_data_hex = ' '.join(f"{byte:02X}" for byte in response.data)
                received_data_dec = ' '.join(str(byte) for byte in response.data)
                vehicle_id = parse_vehicle_id(response.data)
                if vehicle_id is not None and api_vehicle_id is not None:
                    # Convert API value to int for comparison (assuming it's a string)
                    match = (vehicle_id == int(api_vehicle_id))
                break
    except Exception as e:
        print(f"Error while reading CAN messages: {e}")
    finally:
        bus.shutdown()
        status = "Passed" if match else "Failed"
        print(f"Tx_Can_id: {can_id}")
        print(f"Rx Hex: {received_data_hex}")
        print(f"Rx Dec: {received_data_dec}")
        print(f"Vehicle ID: {vehicle_id}")
        print(f"API Vehicle ID: {api_vehicle_id}")
        print(f"Status: {status}")
        return match, api_vehicle_id, vehicle_id

if __name__ == "__MCU_Vehicle_ID__":
    result = MCU_Vehicle_ID()