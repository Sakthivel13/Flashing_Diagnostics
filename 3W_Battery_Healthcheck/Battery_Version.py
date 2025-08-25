import can
from datetime import datetime

# Battery ECU Software Version CAN ID (in hex)
BATTERY_SW_ID = 0x23

def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None

def parse_version(data):
    try:
        major = data[2]
        minor = data[1]
        revision = data[3]
        return f"{major}.{minor}.{revision}"
    except IndexError:
        return "Invalid data length"

def BMS_Version():
    bus = setup_can_bus()
    if not bus:
        return False
    
    version_detected = False
    version = "Not detected"
    received_data_hex = "None"
    received_data_dec = "None"
    can_id = "None"

    try:
        start_time = datetime.now()

        while (datetime.now() - start_time).seconds < 1:
            msg = bus.recv(timeout=0.5)
            if msg and msg.arbitration_id == BATTERY_SW_ID:
                version_detected = True
                can_id = hex(msg.arbitration_id)
                received_data_hex = ' '.join(f"{byte:02X}" for byte in msg.data)
                received_data_dec = ' '.join(str(byte) for byte in msg.data)
                version = parse_version(msg.data)
                break
    except Exception as e:
        print(f"Error while reading CAN messages: {e}")
    finally:
        bus.shutdown()
        status = "Passed" if version_detected else "Failed"
        print(f"Test Sequence: Battery_Version")
        print(f"Tx_Can_id: {can_id}")
        print(f"Rx Hex:{received_data_hex}")
        print(f"Rx Dec:{received_data_dec}")
        print(f"Version: {version}")
        print(f"Status: {status}")
        return version_detected,version

if __name__ == "__main__":
    result = BMS_Version()
