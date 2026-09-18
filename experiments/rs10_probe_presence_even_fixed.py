#!/usr/bin/env python3
"""
One-shot Gamma/RS10 presence probe — fixed EVEN parity.

Why this version:
- No parity reconfiguration after detecting A3.
- No tcflush after TX, so an immediate controller response is not discarded.
- UART stays 9600 8E1 + INPCK + PARMRK throughout.
- With byte 0x06 (two 1-bits), EVEN parity transmits parity bit 0,
  matching the observed physical RS10 response.
- Physical RS10 address 3 MUST be disconnected.
- Default is dry-run. --send transmits exactly ONE byte 0x06.
"""

import argparse, os, select, termios, time

def configure_even(fd):
    a = termios.tcgetattr(fd)
    a[0] = termios.INPCK | termios.PARMRK
    a[1] = 0
    a[2] = termios.CLOCAL | termios.CREAD | termios.CS8 | termios.PARENB
    a[2] &= ~(termios.PARODD | termios.CSTOPB)
    a[3] = 0
    a[4] = termios.B9600
    a[5] = termios.B9600
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIFLUSH)  # only once, before monitoring starts

def decode_parmrk(buf, carry=b""):
    d = carry + buf
    out = []
    i = 0
    while i < len(d):
        if d[i] != 0xff:
            out.append((True, d[i])); i += 1; continue
        if i + 1 >= len(d): break
        if d[i+1] == 0xff:
            out.append((True, 0xff)); i += 2; continue
        if d[i+1] == 0x00:
            if i + 2 >= len(d): break
            out.append((False, d[i+2])); i += 3; continue
        out.append((True, 0xff)); i += 1
    return out, d[i:]

def crc16_kermit(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xffff

def find_10aa_0100(stream):
    for i in range(max(0, len(stream)-256), max(0, len(stream)-7)):
        f = stream[i:i+8]
        if len(f) < 8: continue
        if f[0:5] == bytes.fromhex("82 10 aa 01 00") and f[7] == 0x03:
            c = crc16_kermit(f[1:5])
            if f[5] == (c & 0xff) and f[6] == ((c >> 8) & 0xff):
                return bytes(f)
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--listen", type=float, default=4.0)
    args = ap.parse_args()

    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure_even(fd)
        print("RS10 presence probe — FIXED EVEN parity")
        print("IMPORTANT: physical RS10 address 3 must be DISCONNECTED.")
        print("UART   : 9600 8E1 + INPCK + PARMRK (never reconfigured)")
        print("target : 90x5 -> 21x5 -> 22x5 -> first A3")
        print("TX     : exactly one 06; EVEN parity => parity bit 0")
        print("dry-run:", not args.send)
        print()

        stages = [0x90, 0x21, 0x22]
        stage = 0
        count = 0
        carry = b""
        deadline = time.monotonic() + args.timeout

        while time.monotonic() < deadline:
            r, _, _ = select.select([fd], [], [], 0.2)
            if not r:
                continue
            try:
                raw = os.read(fd, 4096)
            except BlockingIOError:
                continue
            items, carry = decode_parmrk(raw, carry)

            for ok, b in items:
                # Under EVEN parity scan bytes appear as parity errors.
                # PARMRK still preserves the original byte value.
                if stage < 3:
                    want = stages[stage]
                    if b == want:
                        count += 1
                        if count >= 5:
                            print(f"  matched {want:02X} x5")
                            stage += 1
                            count = 0
                    else:
                        count = 0
                    continue

                if b == 0xA3:
                    print(f"  first A3 seen ({'parity OK' if ok else 'parity ERR, expected'})")
                    if not args.send:
                        print("DRY RUN: would send exactly one 06 using the already-active EVEN parity.")
                        return 0

                    t_tx = time.monotonic()
                    os.write(fd, b"\x06")
                    # Don't tcdrain + reconfigure + flush. Keep receiving immediately.
                    print("  SENT exactly one byte: 06 (8E1; no reconfiguration, no RX flush)")

                    end = t_tx + args.listen
                    logical = bytearray()
                    carry2 = b""
                    while time.monotonic() < end:
                        rr, _, _ = select.select([fd], [], [], 0.05)
                        if not rr:
                            continue
                        try:
                            rb = os.read(fd, 4096)
                        except BlockingIOError:
                            continue
                        decoded, carry2 = decode_parmrk(rb, carry2)
                        for _, x in decoded:
                            logical.append(x)
                        f = find_10aa_0100(logical)
                        if f:
                            dt = (time.monotonic() - t_tx) * 1000
                            print(f"*** SUCCESS +{dt:.1f} ms: {f.hex()} ***")
                            return 0
                        if len(logical) > 4096:
                            del logical[:-1024]

                    print("No CRC-valid 10->AA / 0100 seen.")
                    return 1

        print("Scan sequence not seen; NOTHING SENT.")
        return 2
    finally:
        os.close(fd)

if __name__ == "__main__":
    raise SystemExit(main())
