import can
from datetime import datetime

# Battery ECU Presence CAN IDs (in hex)
BATTERY_CAN_IDS = [0x28, 0x2D, 0x2F, 0x22, 0x27, 0x23, 0x26, 0x2E]

def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None

def Battery_Presence():
    bus = setup_can_bus()
    if not bus:
        return False
    
    detected_ids = {}
    presence_detected = False
    start_time = datetime.now()

    try:
        while (datetime.now() - start_time).total_seconds() < 1:
            try:
                msg = bus.recv(timeout=1)
                if msg is None:
                    continue

                if msg.arbitration_id in BATTERY_CAN_IDS:
                    can_id = msg.arbitration_id
                    presence_detected = True
                    if can_id not in detected_ids:
                        detected_ids[can_id] = ' '.join(f"{byte:02X}" for byte in msg.data)
            except can.CanError as ce:
                print(f"[CAN ERROR] {ce}")
            except Exception as e:
                print(f"[ERROR] Unexpected error while receiving CAN: {e}")
                
    finally:
        try:
            bus.shutdown()
        except Exception as e:
            print(f"[WARNING] CAN shutdown issue: {e}")
            
        status = "Passed" if presence_detected else "Failed"
        print(f"Battery_Presence: {status}")
        if presence_detected:
            for can_id, received_data in detected_ids.items():
                print(f"Tx_Can_Id: {hex(can_id)}")
                print(f"Rx_Id: {received_data}")
        else:
            print("Status: Battery ECU not presented")
        print(f"Status: {status}")
        return presence_detected

if __name__ == "__Battery_Presence__":
    Battery_Presence()