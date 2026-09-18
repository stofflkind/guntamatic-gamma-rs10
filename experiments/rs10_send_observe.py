#!/usr/bin/env python3
import argparse
import time
from datetime import datetime
import serial

MODES = {"automatic": 0x00, "heating": 0x03}
MODE_NAMES = {0x00:"automatic",0x03:"heating",0x04:"reduced",0x13:"party",0x14:"away"}

AUTOMATIC_FRAME = bytes.fromhex(
    "82232028062b002a000000000064000900004100090003092a"
    "200000000003002a200000000003002a20000000226903"
)

def crc16_kermit(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xFFFF

def make_mode_frame(mode):
    f = bytearray(AUTOMATIC_FRAME)
    f[10] = MODES[mode]
    c = crc16_kermit(f[1:-3])
    f[-3] = c & 0xff
    f[-2] = (c >> 8) & 0xff
    return bytes(f)

class FFDeinterleaver:
    def __init__(self):
        self.expect_separator = False
    def feed(self, data):
        out = bytearray()
        for b in data:
            if self.expect_separator:
                if b == 0xff:
                    self.expect_separator = False
                    continue
                out.append(b)
                self.expect_separator = True
            else:
                out.append(b)
                self.expect_separator = True
        return bytes(out)

class GammaExtractor:
    def __init__(self):
        self.buf = bytearray()
    def feed(self, data):
        self.buf.extend(data)
        frames = []
        while True:
            try:
                p = self.buf.index(0x82)
            except ValueError:
                self.buf.clear()
                break
            if p:
                del self.buf[:p]
            if len(self.buf) < 4:
                break
            total = self.buf[3] + 8
            if total < 8 or total > 300:
                del self.buf[0]
                continue
            if len(self.buf) < total:
                break
            f = bytes(self.buf[:total])
            if f[-1] != 0x03:
                del self.buf[0]
                continue
            stored = f[-3] | (f[-2] << 8)
            if crc16_kermit(f[1:-3]) != stored:
                del self.buf[0]
                continue
            frames.append(f)
            del self.buf[:total]
        return frames

def type_code(f):
    return (f[3] << 8) | f[4]

def desc2806(f):
    p7 = f[10]
    return f"{f[1]:02X}->{f[2]:02X} 2806 P7={p7:02X} ({MODE_NAMES.get(p7,'unknown')})"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=MODES)
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--guard-ms", type=int, default=500)
    ap.add_argument("--observe-seconds", type=float, default=12.0)
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()

    tx = make_mode_frame(args.mode)
    print(f"mode      : {args.mode} (P7=0x{MODES[args.mode]:02X})")
    print(f"frame     : {tx.hex(' ')}")
    print(f"CRC       : 0x{(tx[-2]<<8 | tx[-3]):04X}")
    print(f"guard     : {args.guard_ms} ms after valid 10->20 / 8001")
    print(f"observe   : {args.observe_seconds:g} s after transmission")
    print(f"dry-run   : {not args.send}")
    if not args.send:
        print("No serial port opened; nothing transmitted.")
        return

    deint = FFDeinterleaver()
    ext = GammaExtractor()

    with serial.Serial(args.port,args.baud,bytesize=serial.EIGHTBITS,
                       parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE,
                       timeout=0.005) as ser:
        print("Listening for end-of-cycle 10->20 / 8001 ...")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            raw = ser.read(256)
            if not raw:
                continue
            for f in ext.feed(deint.feed(raw)):
                if f[1]==0x10 and f[2]==0x20 and type_code(f)==0x8001:
                    print("Found 10->20 / 8001. Guard interval starts.")
                    guard_end = time.monotonic() + args.guard_ms/1000
                    collision = False
                    while time.monotonic() < guard_end:
                        r = ser.read(256)
                        if not r:
                            continue
                        if ext.feed(deint.feed(r)):
                            print("Valid Gamma frame appeared during guard; slot rejected.")
                            collision = True
                            break
                    if collision:
                        continue

                    print("Guard interval clear.")
                    print("TRANSMITTING EXACTLY ONCE...")
                    ser.write(tx)
                    ser.flush()
                    tx_time = time.monotonic()
                    print("Transmission completed. No retry.")
                    print("\nPost-send observation:")

                    obs_end = tx_time + args.observe_seconds
                    c2806 = r2806 = 0
                    while time.monotonic() < obs_end:
                        r = ser.read(256)
                        if not r:
                            continue
                        for f2 in ext.feed(deint.feed(r)):
                            if type_code(f2) != 0x2806:
                                continue
                            dt = (time.monotonic()-tx_time)*1000
                            wall = datetime.now().strftime("%H:%M:%S.%f")
                            print(f"{wall}  {desc2806(f2)}  +{dt:8.1f} ms")
                            if f2[1]==0x10 and f2[2]==0x20:
                                c2806 += 1
                            elif f2[1]==0x23 and f2[2]==0x20:
                                r2806 += 1
                    print(f"\nObserved 2806: controller={c2806}, RS10={r2806}")
                    return
        raise SystemExit("Abort: no suitable 8001 slot found within 30 seconds.")

if __name__ == "__main__":
    main()
