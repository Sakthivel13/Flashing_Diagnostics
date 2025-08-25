import can
from datetime import datetime

# MCU Presence CAN IDs (in hex)
MCU_CAN_IDS = [0xA0, 0xC8, 0x15, 0xB0, 0xAF, 0xAB, 0xB7, 0xCA, 0x668, 0xCB, 0xC7]

def setup_can_bus():
    try:
        return can.interface.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)
    except Exception as e:
        print(f"CAN setup failed: {e}")
        return None

def MCU_Presence():
    bus = setup_can_bus()
    if not bus:
        return False
    
    detected_ids = {}
    presence_detected = False
    start_time = datetime.now()

    try:
        while (datetime.now() - start_time).total_seconds() < 2:
            try:
                msg = bus.recv(timeout=1)
                if msg is None:
                    continue
                if msg.arbitration_id in MCU_CAN_IDS:
                    can_id = msg.arbitration_id
                    presence_detected = True
                    if can_id not in detected_ids:
                        detected_ids[can_id] = ' '.join(f"{byte:02X}" for byte in msg.data)
            except can.CanError as ce:
                print(f"[CAN ERROR] {ce}")
            except Exception as e:
                print(f"[ERROR] Unexpected error while receiving CAN: {e}")

    finally:
        bus.shutdown()
        status = "Passed" if presence_detected else "Failed"
        print(f"MCU_Presence: {status}")
        if presence_detected:
            for can_id, received_data in detected_ids.items():
                print(f"Tx_Can_id: {hex(can_id)}")
                print(f"Rx_Id: {received_data}")
        else:
            print("Status: MCU not presented")
        print(f"Status: {status}")
        return presence_detected

if __name__ == "__MCU_Presence__":
    result = MCU_Presence()