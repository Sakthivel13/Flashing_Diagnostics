# -*- coding: utf-8 -*-
"""
Created on Wed Apr 23 12:07:52 2025
@author: R.Sri Sakthivel
"""

import requests
import json

# Global dictionary to store MAC IDs
mac_ids = {}

def API_CALL(vin_number, api_url):
    """Fetch front and rear TPMS MAC IDs via API call."""
    print("Test_Sequence: API_CALL")
    print(f"API_URL: {api_url}")

    if not api_url or not api_url.startswith("http"):
        print("Status: Failed")
        print("Error: Invalid or empty API URL")
        return (False, "Error")

    try:
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        data = response.json()

        modules = data.get("data", {}).get("modules", [])
        Front_Mac_ID = None
        Rear_Mac_ID = None

        for module in modules:
            if module.get("module") == "IPC":
                for cfg in module.get("configs", []):
                    if cfg.get("refname") == "IPC_TPMSRR_WRITE":
                        Front_Mac_ID = cfg["messages"][0].get("txbytes")
                    elif cfg.get("refname") == "IPC_TPMSFR_WRITE":
                        Rear_Mac_ID = cfg["messages"][0].get("txbytes")

        if Front_Mac_ID and Rear_Mac_ID:
            global mac_ids
            mac_ids['Front Mac ID'] = Front_Mac_ID
            mac_ids['Rear Mac ID'] = Rear_Mac_ID
            value = f"{Front_Mac_ID};{Rear_Mac_ID}"
            print(f"Front_MAC_ID: {Front_Mac_ID}")
            print(f"Rear_MAC_ID: {Rear_Mac_ID}")
            print("Status: Passed")
            return True, Front_Mac_ID, Rear_Mac_ID
        else:
            print("Status: Failed")
            print("Error: Required TX bytes not found in IPC module")
            return (False, "Error")

    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"Status: Failed")
        print(f"Error: API call failed: {e}")
        return (False, "Error")

if __name__ == "__main__":
    # For standalone testing
    test_vin = "MD626AM19S1G16157"
    test_url = f"http://10.121.2.107:3000/vehicles/flashFile/prd/{test_vin}"
    result = API_CALL(test_vin, test_url)
    #print(f"Result: {result}")