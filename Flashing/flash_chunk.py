import time
import can
from typing import Optional, List


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

    def transfer_data(self, block_number: int, data: bytes) -> Optional[List[int]]:
        """0x36: Transfer Data, positive SID=0x76."""
        sid = 0x36
        req = [sid, block_number & 0xFF] + list(data)
        self.tp.manual_transmit(req)
        timeout = self.timings["P2"] / 1000
        resp = self.tp.manual_receive(timeout)
        return resp if resp and resp[0] == sid + 0x40 else None
    
    def tester_present(self) -> Optional[List[int]]:
        req = [0x3E, 0x00]
        timeout = self.timings["P2"] / 1000
        resp = self.tp.send_receive(req, timeout)
        return resp if resp and resp[0] == 0x7E else None


class FlashChunkError(Exception):
    pass


def require(ok, msg: str):
    if not ok:
        raise FlashChunkError(msg)
    return ok


def crc16_ccitt_8408(data: bytes, initial: int = 0x0000) -> int:
    crc = initial
    poly = 0x8408

    for byte in data:
        curr = byte
        for _ in range(8):
            if (crc & 0x0001) ^ (curr & 0x01):
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
            curr >>= 1
    return crc & 0xFFFF


# CRC check


def keep_alive_if_needed(uds, last_time):
    elapsed_ms = (time.time() - last_time) * 1000
    if elapsed_ms >= 5000 / 2:
        resp = uds.tester_present()
        if resp:
            print("[INFO] Tester Present sent")
            return time.time()
        else:
            print("[WARN] Tester Present failed or no response")
    return last_time


def iter_block_chunks(mot_file: str, start_addr: int, length: int, chunk_size: int):
    end = start_addr + length
    buf = bytearray()
    with open(mot_file, "r", encoding="ascii", errors="strict") as f:
        for line in f:
            line = line.strip()
            if not line or line[0] != "S":
                continue
            t = line[1]
            if t not in ("1", "2", "3"):
                continue
            raw = bytes.fromhex(line[2:])
            alen = {"1": 2, "2": 3, "3": 4}[t]
            rec_addr = int.from_bytes(raw[1 : 1 + alen], "big")
            data = raw[1 + alen : -1]

            # emit only the bytes that fall in [start_addr, end)
            for i, b in enumerate(data):
                a = rec_addr + i
                if a < start_addr:
                    continue
                if a >= end:
                    break
                buf.append(b)
                if len(buf) == chunk_size:
                    yield bytes(buf)
                    buf.clear()
            if rec_addr >= end:
                break
    if buf:
        yield bytes(buf)


def flash_chunk(mot_file, address, length, chunk_payload_capacity):
    bus = None
    try:
        bus = can.interface.Bus(
            interface="pcan", channel="PCAN_USBBUS1", bitrate=500000
        )
        bus.set_filters([{"can_id": 0x7E8, "can_mask": 0x7FF}])

        uds = UdsHandler(
            bus,
            tx_id=0x7E0,
            rx_id=0x7E8,
        )
        init_seq = 1
        # Reserve 1 byte for BSC + 1 for SID → adjust if your ECU defines it differently

        seq = init_seq & 0xFF
        last_request_time = time.time()
        bytes_sent = 0
        crc = 0x0000
        print("HHH")
        for chunk in iter_block_chunks(
            mot_file, address, length, chunk_payload_capacity
        ):
            last_request_time = keep_alive_if_needed(uds, last_request_time)
            crc = crc16_ccitt_8408(chunk, crc)
            require(
                uds.transfer_data(seq, chunk),
                f"TransferData failed at seq=0x{seq:02X}",
            )

            # success — report seq used for this chunk
            print("IIII")
            yield True

            bytes_sent += len(chunk)
            seq = 0 if seq == 0xFF else (seq + 1)

        # If we finish the loop cleanly, report success
        print(crc)
        yield ("DONE", True, crc)

    except FlashChunkError as e:
        print(f"[FAIL] {e}")
        return False, None
    except Exception as e:
        print(f"[ERROR] Unexpected: {e}")
        return False, None
    finally:
        if bus is not None:
            try:
                bus.shutdown()
            except Exception as e:
                print(f"[WARN] bus shutdown error: {e}")
if __name__ == "__main__":
    print("hi")
    for result in flash_chunk(r"D:\TVS NIRIX Flashing\N6060929_02 1.mot", 4280287360, 25014, 40):
        print("flash_chunk returned:", result)
