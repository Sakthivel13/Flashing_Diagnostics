import can
from datetime import datetime

# Telematics ECU Presence CAN IDs (in hex)
TELEMATICS_CAN_IDS = [0x701, 0x702, 0x703]

def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None

def Telematics_Presence():
    bus = setup_can_bus()
    if not bus:
        return False
    
    detected_ids = {}
    presence_detected = False

    try:
        start_time = datetime.now()

        while (datetime.now() - start_time).seconds < 1:
            msg = bus.recv(timeout=1)
            if msg and msg.arbitration_id in TELEMATICS_CAN_IDS:
                can_id = msg.arbitration_id
                presence_detected = True
                if can_id not in detected_ids:
                    detected_ids[can_id] = ' '.join(f"{byte:02X}" for byte in msg.data)
    except Exception as e:
        print(f"Error while reading CAN messages: {e}")
    finally:
        bus.shutdown()
        status = "Passed" if presence_detected else "Failed"
        print(f"Telematics_Presence: {status}")
        if presence_detected:
            for can_id, received_data in detected_ids.items():
                print(f"Tx_Can_id: {hex(can_id)}")
                print(f"Rx_Id: {received_data}")
        else:
            print("Status: Telematics ECU not presented")
        print(f"Status: {status}")
        return presence_detected

if __name__ == "__Telematics_Presence__":
    result = Telematics_Presence()