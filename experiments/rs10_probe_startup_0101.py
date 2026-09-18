#!/usr/bin/env python3
"""
RS10 startup probe 0101.
Use ONLY with the physical RS10 (address/heating circuit 3) disconnected.

Waits for controller 10->AA / 0100, then sends exactly one known
RS10 request 23->10 / 0101 after a configurable delay (default 142 ms).
Then listens only. No 2806 is sent.
"""
import argparse,time
from datetime import datetime
import serial

REQ=bytes.fromhex("822310010180f07903")

def crc16(d):
    c=0
    for b in d:
        c^=b
        for _ in range(8):
            c=(c>>1)^0x8408 if c&1 else c>>1
    return c&0xffff

def valid(f):
    return len(f)>=8 and f[0]==0x82 and f[-1]==0x03 and (f[-3]|f[-2]<<8)==crc16(f[1:-3])

def typ(f): return (f[3]<<8)|f[4]

class Deint:
    def __init__(self): self.sep=False
    def feed(self,d):
        o=bytearray()
        for b in d:
            if self.sep and b==0xff:
                self.sep=False; continue
            o.append(b); self.sep=True
        return bytes(o)

class Extract:
    def __init__(self): self.b=bytearray()
    def feed(self,d):
        self.b.extend(d); out=[]
        while True:
            try:i=self.b.index(0x82)
            except ValueError:self.b.clear();break
            if i:del self.b[:i]
            if len(self.b)<4:break
            n=self.b[3]+8
            if n<8 or n>300:del self.b[0];continue
            if len(self.b)<n:break
            f=bytes(self.b[:n])
            if not valid(f):del self.b[0];continue
            out.append(f);del self.b[:n]
        return out

ap=argparse.ArgumentParser()
ap.add_argument("--port",default="/dev/ttyUSB1")
ap.add_argument("--delay-ms",type=float,default=142.0)
ap.add_argument("--observe",type=float,default=4.0)
ap.add_argument("--send",action="store_true")
a=ap.parse_args()

print("RS10 startup 0101 probe")
print("IMPORTANT: physical RS10 address 3 must be disconnected.")
print("request :",REQ.hex())
print("CRC     :","OK" if valid(REQ) else "INVALID")
print("delay   :",a.delay_ms,"ms after 10->AA/0100")
print("dry-run :",not a.send)
if not a.send: raise SystemExit

D=Deint();E=Extract()
with serial.Serial(a.port,9600,bytesize=8,parity="N",stopbits=1,timeout=.002) as s:
    print("\nWaiting up to 30 s for 10->AA 0100 ...")
    trigger=None
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        raw=s.read(256)
        if not raw:continue
        for f in E.feed(D.feed(raw)):
            if f[1]==0x10 and f[2]==0xaa and typ(f)==0x0100:
                trigger=time.monotonic()
                print(datetime.now().strftime("%H:%M:%S.%f"),
                      "TRIGGER",f.hex())
                break
        if trigger is not None:break
    if trigger is None:
        raise SystemExit("No 10->AA/0100 seen; NOTHING SENT.")

    target=trigger+a.delay_ms/1000
    while time.monotonic()<target:
        time.sleep(.0005)
    s.write(REQ);s.flush();sent=time.monotonic()
    print(datetime.now().strftime("%H:%M:%S.%f"),
          f"SENT ONCE 23->10 0101 (actual delay {(sent-trigger)*1000:.2f} ms)")
    print("Listening only...\n")

    count=0
    end=sent+a.observe
    while time.monotonic()<end:
        raw=s.read(256)
        if not raw:continue
        for f in E.feed(D.feed(raw)):
            count+=1
            tc=typ(f); ms=(time.monotonic()-sent)*1000
            mark=""
            if f[1]==0x10 and f[2]==0x20 and tc==0x8001:
                mark="  <== 8001 RESPONSE"
            print(f"{datetime.now().strftime('%H:%M:%S.%f')} +{ms:8.1f} ms "
                  f"{f[1]:02X}->{f[2]:02X} {tc:04X} HEX={f.hex()}{mark}")
    print("\nObserved CRC-valid frames:",count)
