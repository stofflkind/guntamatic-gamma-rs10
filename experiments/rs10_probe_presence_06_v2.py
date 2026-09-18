#!/usr/bin/env python3
import argparse, time, sys
import serial

PORT="/dev/ttyUSB1"
BAUD=9600

def crc16_kermit(data: bytes) -> int:
    crc=0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xffff

def parse_frames(buf):
    out=[]
    i=0
    while i < len(buf):
        try:
            s=buf.index(0x82,i)
        except ValueError:
            return out, bytearray()
        if len(buf)-s < 8:
            return out, buf[s:]
        ll=buf[s+3]
        total=ll+8
        if len(buf)-s < total:
            return out, buf[s:]
        fr=bytes(buf[s:s+total])
        if fr[-1] == 0x03:
            got=fr[-3] | (fr[-2]<<8)
            if got == crc16_kermit(fr[1:-3]):
                out.append(fr)
                i=s+total
                continue
        i=s+1
    return out, bytearray()

class FFDecoder:
    def __init__(self):
        self.logical=bytearray()
        self.after_ff=False
    def feed(self,b):
        if self.after_ff:
            self.logical.append(b)
            self.after_ff=False
        elif b == 0xff:
            self.after_ff=True
        else:
            self.logical.append(b)
        if len(self.logical)>4096:
            del self.logical[:-2048]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--port", default=PORT)
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--listen", type=float, default=4.0)
    # A 9600 8N1 byte is ~1.04 ms. Observed scan bytes are separated by
    # ~15-32 ms, so 8 ms cleanly separates them from bytes inside frames.
    ap.add_argument("--gap-ms", type=float, default=8.0)
    a=ap.parse_args()

    print("RS10 presence 0x06 probe v2")
    print("IMPORTANT: physical RS10 address 3 must be DISCONNECTED.")
    print("Detects scan bytes by inter-byte silence, not by raw byte value alone.")
    print("target  : 90x5 -> 21x5 -> 22x5 -> first A3")
    print("TX byte : 06")
    print("gap     :", a.gap_ms, "ms")
    print("dry-run :", not a.send)
    print()

    ser=serial.Serial(a.port,BAUD,bytesize=8,parity='N',stopbits=1,
                      timeout=0.002,xonxoff=False,rtscts=False,dsrdtr=False)
    ser.reset_input_buffer()

    expected=[0x90,0x21,0x22]
    state=0
    count=0
    prev_t=None
    start=time.monotonic()
    trigger_t=None

    print(f"Waiting up to {a.timeout:.0f} s for scan sequence ...")
    try:
        while time.monotonic()-start < a.timeout:
            d=ser.read(1)
            if not d:
                continue
            now=time.monotonic()
            b=d[0]
            gap_ms = None if prev_t is None else (now-prev_t)*1000
            prev_t=now

            # Only bytes preceded by a substantial silent interval are treated
            # as short scan tokens. Bytes inside normal/interleaved frames are ignored.
            if gap_ms is None or gap_ms < a.gap_ms:
                continue

            if state < 3:
                want=expected[state]
                if b == want:
                    count += 1
                    if count == 5:
                        print(f"  matched {want:02X} x5")
                        state += 1
                        count = 0
                else:
                    # Conservative resync.
                    if b == 0x90:
                        state=0
                        count=1
                    elif b in (0x21,0x22,0xA3):
                        count=0
                    # unrelated short token: leave state but don't advance
            else:
                if b == 0xA3:
                    trigger_t=time.monotonic()
                    print("  first A3 seen")
                    if a.send:
                        ser.write(b"\x06")
                        ser.flush()
                        print("  SENT exactly one byte: 06")
                    else:
                        print("  DRY RUN: would send exactly one byte: 06")
                    break
                elif b == 0x90:
                    # We missed A3; restart next scan.
                    state=0
                    count=1

        if trigger_t is None:
            print("Scan sequence not seen; NOTHING SENT.")
            return 2

        print(f"Listening {a.listen:.1f} s for CRC-valid 10->AA / 0100 ...")
        dec=FFDecoder()
        deadline=time.monotonic()+a.listen
        while time.monotonic() < deadline:
            data=ser.read(256)
            if not data:
                continue
            for b in data:
                dec.feed(b)
            frames, rem=parse_frames(dec.logical)
            dec.logical=rem
            for fr in frames:
                src,dst,ll=fr[1],fr[2],fr[3]
                typ=(ll<<8)|fr[4]
                dt=(time.monotonic()-trigger_t)*1000
                print(f"  +{dt:7.1f} ms {src:02X}->{dst:02X} type={typ:04X} {fr.hex()}")
                if src==0x10 and dst==0xAA and typ==0x0100:
                    print("*** SUCCESS: controller emitted 10->AA / 0100 ***")
                    return 0

        print("No CRC-valid 10->AA / 0100 seen.")
        return 1
    finally:
        ser.close()

if __name__=="__main__":
    raise SystemExit(main())
