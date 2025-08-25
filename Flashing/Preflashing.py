import time
import can
from typing import Optional, List
import ctypes
from ctypes import c_ubyte, c_int, POINTER
import Crypto
from Crypto.Cipher import AES


class IsoTpHandler:
    def __init__(self, bus: can.Bus, tx_id: int, rx_id: int):
        self.bus = bus
        self.tx_id = tx_id
        self.rx_id = rx_id

    # ── CAN-level primitives ─────────────────────────────────────
    def _log_message(self, direction: str, msg: can.Message):
        data_str = " ".join(f"{b:02X}" for b in msg.data)
        log_line = (
            f"{direction} ID=0x{msg.arbitration_id:X} DLC={msg.dlc} DATA={data_str}"
        )

        # Print to terminal
        print(log_line)

        # Save to file (append mode)
        with open("uds_log.txt", "a") as log_file:
            log_file.write(log_line + "\n")

    def send_raw_can(self, data: list[int]):
        msg = can.Message(
            arbitration_id=self.tx_id,
            data=bytearray(data),
            is_extended_id=False,
            is_fd=False,
        )
        self._log_message("[TX]", msg)
        try:
            self.bus.send(msg)
        except can.CanError as e:
            print(f"[ERROR] CAN send failed: {e}")

    def recv_raw_can(self, timeout: float = 2.0) -> can.Message | None:
        start = time.time()
        while time.time() - start < timeout:
            msg = self.bus.recv(timeout=0.3)
            if msg:
                self._log_message("[RX]", msg)
                if msg.arbitration_id == self.rx_id:
                    return msg
        print("no message received")
        return None

    # ── ISO-TP framing helpers ────────────────────────────────────
    @staticmethod
    def build_single_frame(payload: list[int]) -> list[int]:
        pci = len(payload) & 0x0F  # SF: lead nibble = 0x0, low nibble = length
        frame = [pci] + payload
        frame += [0x00] * (8 - len(frame))  # pad to 8 bytes
        return frame

    @staticmethod
    def build_first_frame(payload: list[int]) -> tuple[list[int], list[int]]:
        total = len(payload)
        pci = 0x10 | (
            (total >> 8) & 0x0F
        )  # FF: lead nibble = 0x1, low nibble = high length bits
        ff = [pci, total & 0xFF] + payload[:6]
        ff += [0x00] * (8 - len(ff))
        return ff, payload[6:]

    @staticmethod
    def build_consecutive_frame(chunk: list[int], seq: int) -> list[int]:
        pci = 0x20 | (seq & 0x0F)  # CF: lead nibble = 0x2, low nibble = sequence
        cf = [pci] + chunk
        cf += [0x00] * (8 - len(cf))
        return cf

    @staticmethod
    def parse_flow_control(msg: can.Message) -> tuple[int, float]:
        # consider adding for 0x31 meaning wait for a while

        if not msg or (msg.data[0] & 0xF0) != 0x30:
            raise ValueError("[ERROR] No or invalid Flow Control Frame")
        bs = msg.data[1]
        stmin_raw = msg.data[2]
        if stmin_raw <= 0x7F:
            stmin = stmin_raw / 1000
        elif 0xF1 <= stmin_raw <= 0xF9:
            stmin = (stmin_raw - 0xF0) / 10000
        else:
            stmin = 0
        return bs, stmin

    # ── ISO-TP transport primitives ───────────────────────────────
    def manual_transmit(self, payload: list[int], retry_limit: int = 3):
        print(f"[INFO] Transmitting {len(payload)} bytes via ISO-TP")

        # Single Frame
        if len(payload) <= 7:
            sf = self.build_single_frame(payload)
            self.send_raw_can(sf)
            return

        # Multi-Frame (First Frame + Consecutives)
        ff, remainder = self.build_first_frame(payload)
        for attempt in range(1, retry_limit + 1):
            print(f"[INFO] Sending First Frame (attempt {attempt})")
            self.send_raw_can(ff)
            fc = self.recv_raw_can()
            flow_status = fc.data[0] & 0xF0
            if fc and flow_status == 0x30:
                bs, stmin = self.parse_flow_control(fc)
                break
            elif flow_status == 0x31:
                raise RuntimeError("FC: Wait (0x31) not supported")
            elif flow_status == 0x32:
                raise RuntimeError("FC: Overflow (0x32) — ECU buffer full")
            elif attempt == retry_limit:
                raise RuntimeError("No valid Flow Control received")
        seq = 1
        sent = 0
        block = 0
        while sent < len(remainder):
            chunk = remainder[sent : sent + 7]
            cf = self.build_consecutive_frame(chunk, seq)
            self.send_raw_can(cf)
            sent += len(chunk)
            seq = (seq + 1) % 16
            block += 1
            time.sleep(stmin)
            if bs and block >= bs:
                # might need an attempt block
                fc = self.recv_raw_can()
                if not fc:
                    raise RuntimeError("Expected Flow Control but none received")
                bs, stmin = self.parse_flow_control(fc)
                block = 0

    def manual_receive(self, timeout: float = 2.0) -> list[int] | None:
        """
        Receive a complete ISO-TP payload (handles SF or FF+CF).
        Returns the raw payload bytes (no PCI) or None on timeout/error.
        """
        first = self.recv_raw_can(timeout)
        if not first:
            return None

        pci_type = (first.data[0] & 0xF0) >> 4

        if pci_type == 0x0 and (first.data[0] & 0x0F) > 0:
            if first.data[1] == 0x7F:
                print("[UDS ERROR] Negative response:", first.data[2])
                return None

        # Single Frame
        if pci_type == 0x0:
            length = first.data[0] & 0x0F
            return list(first.data[1 : 1 + length])

        # First Frame + Consecutives
        elif pci_type == 0x1:
            total = ((first.data[0] & 0x0F) << 8) + first.data[1]
            data = list(first.data[2:])
            # send Flow-Control (CTS)
            self.send_raw_can([0x30, 0x00, 0x00] + [0] * 5)
            seq = 1
            while len(data) < total:
                cf = self.recv_raw_can(timeout)
                if not cf:
                    return None
                if (cf.data[0] & 0x0F) != seq:
                    raise RuntimeError(
                        f"Sequence mismatch: expected {seq}, got {cf.data[0] & 0x0F}"
                    )
                data.extend(cf.data[1:])
                seq = (seq + 1) % 16
            return data[:total]

        raise RuntimeError(f"Unknown PCI type {pci_type}")

    def send_receive(
        self, request: list[int], timeout: float = 5.0
    ) -> list[int] | None:
        # Always SF for request
        sf = self.build_single_frame(request)
        self.send_raw_can(sf)
        # Now receive the response (may be SF or MF)
        return self.manual_receive(timeout)


class UdsHandler:

    def __init__(self, bus, tx_id, rx_id, timings=None):
        self.tp = IsoTpHandler(bus, tx_id, rx_id)
        self.timings = timings or {"P2": 500, "P2*": 5000, "S3": 5000}
        # P2 - WAIT TIME BTW REQ & RESP
        # P2* - WAIT TIME BETWEEN RETRIES
        # S3 - MAX WAIT TIME IN NON-DEFAULT SESS BTW REQ

    def diagnostic_session_control(
        self, session_type: int = 0x03
    ) -> Optional[List[int]]:
        """0x10: Diagnostic Session Control, positive SID=0x50."""
        req = [0x10, session_type]
        timeout = self.timings["P2"] / 1000
        resp = self.tp.send_receive(req, timeout)
        return resp if resp and resp[0] == 0x50 else None

    def control_dtc_settings(
        self, setting_type: int = 0x02, dtc_setting_record: bytes = b""
    ) -> Optional[List[int]]:
        """0x85: Control DTC Settings, positive SID=0xC5."""
        req = [0x85, setting_type] + list(dtc_setting_record)
        timeout = self.timings["P2"] / 1000
        resp = self.tp.send_receive(req, timeout)
        return resp if resp and resp[0] == 0xC5 else None

    def ecu_reset(self, reset_type: int = 0x01) -> Optional[List[int]]:
        """0x11: ECU Reset, positive SID=0x51."""
        req = [0x11, reset_type]
        timeout = self.timings["P2"] / 1000
        resp = self.tp.send_receive(req, timeout)
        return resp if resp and resp[0] == 0x51 else None

    def request_seed(self, level: int = 0x01) -> Optional[bytes]:
        """0x27: Security Access - Request Seed, positive SID=0x67."""
        timeout = self.timings["P2"] / 1000
        raw = self.tp.send_receive([0x27, level], timeout)
        return bytes(raw[2:]) if raw and raw[0] == 0x67 else None

    def send_key(self, key: bytes, level: int = 0x01) -> Optional[List[int]]:
        """0x27: Security Access - Send Key, positive SID=0x67."""
        req = [0x27, level + 1] + list(key)
        self.tp.manual_transmit(req)
        timeout = self.timings["P2"] / 1000
        resp = self.tp.manual_receive(timeout)
        return resp if resp and resp[0] == 0x67 else None

    def tester_present(self) -> Optional[List[int]]:
        req = [0x3E, 0x00]
        timeout = self.timings["P2"] / 1000
        resp = self.tp.send_receive(req, timeout)
        return resp if resp and resp[0] == 0x7E else None


def calculate_key_from_seed(
    seed_bytes: bytes,
    dll_path: str,
    key_length: int = 4,
    security_level: int = 1,
) -> bytes | None:
    try:
        # Load DLL (try cdecl first, fallback to stdcall)
        try:
            lib = ctypes.CDLL(dll_path)
        except OSError:
            lib = ctypes.WinDLL(dll_path)

        # Map security level to value (adjust this mapping if needed)
        value = (security_level - 1) // 2

        # Initialize the DLL for the security level
        init_func = lib.SedKeyGen_Init
        init_func.argtypes = [c_int]
        init_func.restype = c_int
        init_result = init_func(value)
        if init_result != 0:
            print(f"[ERROR] Initialization failed with code {init_result}")
            return None

        # Prepare GetKey function
        func = lib.SedKeyGen_GetKey
        # Signature: int SedKeyGen_GetKey(int level, const uint8_t* seed, uint8_t* key)
        func.argtypes = [c_int, POINTER(c_ubyte), POINTER(c_ubyte)]
        func.restype = c_int  # error code

        seed_len = len(seed_bytes)
        seed_array = (c_ubyte * seed_len)(*seed_bytes)
        key_array = (c_ubyte * key_length)()  # output buffer for key

        # Call the function with security level, seed pointer, and key buffer pointer
        result = func(value, seed_array, key_array)
        if result != 0:
            print(f"[ERROR] Key generation failed with error code: {result}")
            return None

        # Return the generated key as bytes
        return bytes(key_array)

    except Exception as e:
        print(f"[ERROR] Exception calling DLL function: {e}")
        return None


def keep_alive_if_needed(uds, last_time):
    elapsed_ms = (time.time() - last_time) * 1000
    if elapsed_ms >= 5000 / 2:
        resp = UdsHandler.tester_present()
        if resp:
            print("[INFO] Tester Present sent")
            return time.time()
        else:
            print("[WARN] Tester Present failed or no response")
    return last_time


def encrypt_seed(seed, level):
    if not seed or len(seed) != 16:
        return None
    if level == 3:
        prv_key = bytes.fromhex(
            "E6AB4112C0FBD97834DAA6606FA45D65"
        )  # For first security access (03/04)
    else:
        prv_key = bytes.fromhex(
            "DCDEE01FAB9D7AB77B49C9FFD075B364"
        )  # For second security access (01/02)
    cipher = AES.new(prv_key, AES.MODE_ECB)
    encrypted_full = cipher.encrypt(seed)
    print(f"Encrypted Key: {encrypted_full.hex()}")
    print("AES Encryption Passed\n")

    return encrypted_full


class PreflashError(Exception):
    pass


def require(ok, msg: str):
    """Raise on falsy result; return the value otherwise."""
    if not ok:
        raise PreflashError(msg)
    return ok


def Preflashing():
    try:
        bus = can.interface.Bus(
            interface="pcan", channel="PCAN_USBBUS1", bitrate=500000
        )
        bus.set_filters([{"can_id": 0x7E8, "can_mask": 0x7FF}])

        uds = UdsHandler(bus, tx_id=0x7E0, rx_id=0x7E8)

        last_request_time = time.time()

        # 0x01 default session
        resp = require(
            uds.diagnostic_session_control(0x01), "Session control (0x01) failed"
        )
        print(f"[OK] Session started: {resp}")

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        # 0x03 programming/extended session
        resp = require(
            uds.diagnostic_session_control(0x03), "Session control (0x03) failed"
        )
        print(f"[OK] Session started: {resp}")

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        # Security 0x03: seed/key
        seed = require(uds.request_seed(0x03), "Seed request (0x03) failed")
        print(f"[OK] Seed returned: {seed}")

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        my_key = require(encrypt_seed(seed, 3), "Encrypt seed (level 3) failed")
        print("calculated key: ", my_key)

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        resp = require(uds.send_key(my_key, 0x03), "Send key (0x03) failed")
        print(f"[OK] Unlock successful: {resp}")

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        # DTC off
        resp = uds.control_dtc_settings(0x02)
        print(f"[OK] DTC off: {resp}")

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        # Back to sessions + second security
        resp = require(
            uds.diagnostic_session_control(0x01), "Session control (0x01) failed"
        )
        print(f"[OK] Session started: {resp}")

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        resp = require(
            uds.diagnostic_session_control(0x02), "Session control (0x02) failed"
        )
        print(f"[OK] Session started: {resp}")

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        seed = require(uds.request_seed(0x01), "Seed request (0x01) failed")
        print(f"[OK] Seed returned: {seed}")

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        my_key = require(encrypt_seed(seed, 1), "Encrypt seed (level 1) failed")
        print("calculated key: ", my_key)

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        resp = require(uds.send_key(my_key, 0x01), "Send key (0x01) failed")
        print(f"[OK] Unlock successful: {resp}")

        last_request_time = keep_alive_if_needed(uds, last_request_time)

        # Reset
        resp = require(uds.ecu_reset(0x60), "ECU reset (0x11/0x60) failed")
        print(f"[OK] Reset successful: {resp}")

        print("preflashing successful")
        return True

    except PreflashError as e:
        print(f"[FAIL] {e}")
        return False
    except Exception as e:
        # Optional: distinguish unexpected errors
        print(f"[ERROR] Unexpected: {e}")
        return False
    finally:
        if bus is not None:
            try:
                bus.shutdown()
            except Exception as e:
                print(f"[WARN] bus shutdown error: {e}")
if __name__ == "__main__":
    Preflashing()
