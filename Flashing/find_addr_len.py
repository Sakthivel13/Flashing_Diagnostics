import time
import can
from typing import List, Tuple


# --- helpers (match your existing pattern) ---
class FindAddrLenError(Exception):
    pass


def require(ok, msg: str):
    if not ok:
        raise FindAddrLenError(msg)
    return ok


# --------------------------------------------


def find_addr_len(mot_file_path):

    try:
        mem = {}

        # Open as strict ASCII; S-records are ASCII by spec
        with open(mot_file_path, "r", encoding="ascii", errors="strict") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line or line[0] != "S":
                    continue

                rectype = line[1]
                if rectype not in ("1", "2", "3"):
                    # Only consider data records
                    continue

                hexpart = line[2:]
                try:
                    payload = bytes.fromhex(hexpart)
                except ValueError as e:
                    raise FindAddrLenError(f"Line {lineno}: invalid hex — {e}")

                addr_len_map = {"1": 2, "2": 3, "3": 4}
                alen = addr_len_map[rectype]

                # payload layout: [count][addr...][data...][checksum]
                require(
                    len(payload) >= 1 + alen + 1,
                    f"Line {lineno}: S{rectype} too short (len={len(payload)})",
                )

                addr = int.from_bytes(payload[1 : 1 + alen], "big")
                data = payload[1 + alen : -1]  # exclude checksum (no validation here)

                # Accumulate bytes into memory map
                for i, b in enumerate(data):
                    mem[addr + i] = b

        if not mem:
            return []

        # Build contiguous blocks
        addrs = sorted(mem.keys())
        blocks: List[Tuple[int, int]] = []
        start = addrs[0]
        prev = start

        for a in addrs[1:]:
            if a == prev + 1:
                prev = a
                continue
            # close previous block
            blocks.append((start, prev - start + 1))
            start = a
            prev = a

        # close final block
        blocks.append((start, prev - start + 1))
        print(blocks)
        return blocks

    except FindAddrLenError as e:
        print(f"[FAIL] {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected: {e}")
        return False
if __name__ == "__main__":
    find_addr_len(r"D:\TVS NIRIX Flashing\N6060929_02 1.mot")
