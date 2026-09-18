#!/usr/bin/env python3
"""
Single-shot RS10 emulator probe: 23->10 / 0105.
Use ONLY while the physical RS10 (heating-circuit address 3) is disconnected.
Sends no 2806 and changes no known parameter.
"""
import argparse, time
from datetime import datetime
import serial

PROBE = bytes.fromhex("822310010510198a03")

def crc16_kermit(data):
    c=0
    for b in data:
        c ^= b
        for _ in range(8):
            c=(c>>1)^0x8408 if c&1 else c>>1
    return c & 0xffff

def valid(f):
    return len(f)>=8 and f[0]==0x82 and f[-1]==0x03 and \
           (f[-3] | (f[-2]<<8)) == crc16_kermit(f[1:-3])

class Deint:
    def __init__(self): self.sep=False
    def feed(self,d):
        o=bytearray()
        for b in d:
            if self.sep and b==0xff:
                self.sep=False
                continue
            o.append(b); self.sep=True
        return bytes(o)

class Extract:
    def __init__(self): self.b=bytearray()
    def feed(self,d):
        self.b.extend(d); out=[]
        while True:
            try: i=self.b.index(0x82)
            except ValueError: self.b.clear(); break
            if i: del self.b[:i]
            if len(self.b)<4: break
            n=self.b[3]+8
            if n<8 or n>300: del self.b[0]; continue
            if len(self.b)<n: break
            f=bytes(self.b[:n])
            if not valid(f): del self.b[0]; continue
            out.append(f); del self.b[:n]
        return out

def typ(f): return (f[3]<<8)|f[4]

ap=argparse.ArgumentParser()
ap.add_argument("--port", default="/dev/ttyUSB1")
ap.add_argument("--observe", type=float, default=5.0)
ap.add_argument("--send", action="store_true")
a=ap.parse_args()

print("RS10 0105 single-shot probe")
print("IMPORTANT: physical RS10 address 3 must be disconnected.")
print("probe   :", PROBE.hex())
print("CRC     :", "OK" if valid(PROBE) else "INVALID")
print("dry-run :", not a.send)
if not a.send:
    raise SystemExit

D=Deint(); E=Extract()
with serial.Serial(a.port,9600,bytesize=8,parity="N",stopbits=1,timeout=.005) as s:
    # Wait for 250 ms without a CRC-valid Gamma frame.
    last=time.monotonic(); begin=last
    while True:
        raw=s.read(256)
        if raw and E.feed(D.feed(raw)):
            last=time.monotonic()
        if time.monotonic()-last >= .250:
            break
        if time.monotonic()-begin > 10:
            raise SystemExit("No valid-frame gap found; nothing sent.")

    s.write(PROBE); s.flush()
    sent=time.monotonic()
    print("\nSENT ONCE: 23->10 0105")
    print("Listening only...\n")

    count=0
    while time.monotonic()-sent < a.observe:
        raw=s.read(256)
        if not raw: continue
        for f in E.feed(D.feed(raw)):
            count += 1
            ms=(time.monotonic()-sent)*1000
            marker = "  <== POSSIBLE RESPONSE" if typ(f)==0x1005 else ""
            print(f"{datetime.now().strftime('%H:%M:%S.%f')} +{ms:8.1f} ms "
                  f"{f[1]:02X}->{f[2]:02X} {typ(f):04X} "
                  f"HEX={f.hex()}{marker}")
    print("\nObserved CRC-valid frames:", count)
