#!/usr/bin/env python3
import argparse,time
from datetime import datetime
import serial

PROBE=bytes.fromhex("8223aa0100019b4803")

def crc(data):
    c=0
    for b in data:
        c ^= b
        for _ in range(8):
            c=(c>>1)^0x8408 if c&1 else c>>1
    return c&0xffff

def valid(f):
    return len(f)>=8 and f[0]==0x82 and f[-1]==0x03 and (f[-3]|f[-2]<<8)==crc(f[1:-3])

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
ap.add_argument("--port",default="/dev/ttyUSB1")
ap.add_argument("--observe",type=float,default=10)
ap.add_argument("--send",action="store_true")
a=ap.parse_args()

print("RS10 minimal emulator probe")
print("IMPORTANT: physical RS10 on address 3 must be disconnected.")
print("probe:",PROBE.hex(),"CRC:", "OK" if valid(PROBE) else "INVALID")
print("dry-run:",not a.send)
if not a.send: raise SystemExit

D=Deint(); E=Extract()
with serial.Serial(a.port,9600,bytesize=8,parity="N",stopbits=1,timeout=.005) as s:
    last=time.monotonic(); start=last
    while True:
        r=s.read(256)
        if r and E.feed(D.feed(r)): last=time.monotonic()
        if time.monotonic()-last>=.250: break
        if time.monotonic()-start>10: raise SystemExit("No valid-frame gap found; nothing sent.")
    s.write(PROBE); s.flush(); sent=time.monotonic()
    print("SENT ONCE: 23->AA 0100; now listening only")
    count=0
    while time.monotonic()-sent<a.observe:
        r=s.read(256)
        if not r: continue
        for f in E.feed(D.feed(r)):
            count+=1
            print(f"{datetime.now().strftime('%H:%M:%S.%f')} +{(time.monotonic()-sent)*1000:8.1f} ms "
                  f"{f[1]:02X}->{f[2]:02X} {typ(f):04X} HEX={f.hex()}")
    print("Observed CRC-valid frames:",count)
