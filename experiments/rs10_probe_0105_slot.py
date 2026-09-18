#!/usr/bin/env python3
"""
RS10 slot probe: wait for 10->AA/0100, then send one 23->10/0105
after a configurable delay (default 130 ms).

ONLY use while the physical RS10 on heating-circuit address 3 is disconnected.
No 2806 is transmitted.
"""
import argparse, time
from datetime import datetime
import serial

REQ = bytes.fromhex("822310010510198a03")

def crc16(data):
    c=0
    for b in data:
        c ^= b
        for _ in range(8):
            c=(c>>1)^0x8408 if c&1 else c>>1
    return c & 0xffff

def valid(f):
    return len(f)>=8 and f[0]==0x82 and f[-1]==0x03 and \
           (f[-3] | f[-2]<<8)==crc16(f[1:-3])

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
ap.add_argument("--delay-ms",type=float,default=130.0)
ap.add_argument("--observe",type=float,default=3.0)
ap.add_argument("--send",action="store_true")
a=ap.parse_args()

print("RS10 timed 0105 slot probe")
print("IMPORTANT: physical RS10 address 3 must be disconnected.")
print("request :",REQ.hex())
print("CRC     :","OK" if valid(REQ) else "INVALID")
print("delay   :",a.delay_ms,"ms after 10->AA/0100")
print("dry-run :",not a.send)
if not a.send: raise SystemExit

D=Deint(); E=Extract()
with serial.Serial(a.port,9600,bytesize=8,parity="N",stopbits=1,timeout=.002) as s:
    print("\nWaiting for 10->AA 0100 ...")
    trigger=None
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        raw=s.read(256)
        if not raw: continue
        for f in E.feed(D.feed(raw)):
            if f[1]==0x10 and f[2]==0xaa and typ(f)==0x0100:
                trigger=time.monotonic()
                print(datetime.now().strftime("%H:%M:%S.%f"),"TRIGGER 10->AA 0100")
                break
        if trigger is not None: break

    if trigger is None:
        raise SystemExit("No 10->AA/0100 seen within 20 s; NOTHING SENT.")

    target=trigger+a.delay_ms/1000.0
    while time.monotonic()<target:
        time.sleep(0.0005)

    s.write(REQ); s.flush()
    sent=time.monotonic()
    print(datetime.now().strftime("%H:%M:%S.%f"),
          f"SENT 23->10 0105 (actual delay {(sent-trigger)*1000:.2f} ms)")
    print("Listening only...\n")

    end=sent+a.observe
    count=0
    while time.monotonic()<end:
        raw=s.read(256)
        if not raw: continue
        for f in E.feed(D.feed(raw)):
            count+=1
            ms=(time.monotonic()-sent)*1000
            mark="  <== 1005 RESPONSE" if f[1]==0x10 and f[2]==0x20 and typ(f)==0x1005 else ""
            print(f"{datetime.now().strftime('%H:%M:%S.%f')} +{ms:8.1f} ms "
                  f"{f[1]:02X}->{f[2]:02X} {typ(f):04X} HEX={f.hex()}{mark}")
    print("\nObserved CRC-valid frames:",count)
