#!/usr/bin/env python3
"""
One-shot Gamma/RS10 presence probe using Linux CMSPAR (mark/space parity).

SAFETY:
- Physical RS10 at address 3 MUST be disconnected.
- Sends exactly ONE data byte (0x06), once.
- No 2806 / no operating-mode write.
- Default is DRY RUN. Add --send for the single active test.

Observed reference:
- Scan token A3 is received with ODD parity OK.
- RS10 response 06 is received with EVEN parity OK.
For byte 0x06 (two '1' data bits), EVEN parity emits parity bit 0.
We therefore transmit 0x06 using SPACE parity (CMSPAR, parity bit always 0).
"""

import argparse, os, select, termios, time

CMSPAR = getattr(termios, "CMSPAR", 0x40000000)

def set_rx_odd(fd):
    a=termios.tcgetattr(fd)
    a[0]=termios.INPCK | termios.PARMRK
    a[1]=0
    a[2]=termios.CLOCAL|termios.CREAD|termios.CS8|termios.PARENB|termios.PARODD
    a[2] &= ~termios.CSTOPB
    a[3]=0
    a[4]=termios.B9600; a[5]=termios.B9600
    a[6][termios.VMIN]=0; a[6][termios.VTIME]=1
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIFLUSH)

def set_space(fd):
    a=termios.tcgetattr(fd)
    a[0]=0; a[1]=0
    a[2]=termios.CLOCAL|termios.CREAD|termios.CS8|termios.PARENB|CMSPAR
    a[2] &= ~(termios.PARODD|termios.CSTOPB)  # CMSPAR + !PARODD => SPACE, bit 0
    a[3]=0
    a[4]=termios.B9600; a[5]=termios.B9600
    a[6][termios.VMIN]=0; a[6][termios.VTIME]=1
    termios.tcsetattr(fd, termios.TCSANOW, a)

def parmrk_items(buf, carry=b""):
    d=carry+buf; out=[]; i=0
    while i<len(d):
        if d[i]!=0xff:
            out.append((True,d[i])); i+=1; continue
        if i+1>=len(d): break
        if d[i+1]==0xff:
            out.append((True,0xff)); i+=2; continue
        if d[i+1]==0x00:
            if i+2>=len(d): break
            out.append((False,d[i+2])); i+=3; continue
        out.append((True,0xff)); i+=1
    return out,d[i:]

def crc16_kermit(data):
    crc=0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc=(crc>>1)^0x8408 if crc&1 else crc>>1
    return crc & 0xffff

def valid_10aa_0100(stream):
    # Logical frame: 82 10 AA 01 00 crcLo crcHi 03
    for i in range(max(0,len(stream)-64),len(stream)-7):
        f=stream[i:i+8]
        if f[0]==0x82 and f[1]==0x10 and f[2]==0xaa and f[3]==0x01 and f[4]==0x00 and f[7]==0x03:
            c=crc16_kermit(f[1:5])
            if f[5]==(c&0xff) and f[6]==(c>>8):
                return bytes(f)
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--port",default="/dev/ttyUSB1")
    ap.add_argument("--send",action="store_true")
    ap.add_argument("--timeout",type=float,default=30.0)
    ap.add_argument("--listen",type=float,default=4.0)
    args=ap.parse_args()

    fd=os.open(args.port, os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
    try:
        set_rx_odd(fd)
        print("RS10 presence MARK/SPACE probe")
        print("IMPORTANT: physical RS10 address 3 must be DISCONNECTED.")
        print("RX     : 9600 8O1 + INPCK + PARMRK")
        print("target : first parity-OK A3 after scan progression 90 -> 21 -> 22")
        print("TX     : 06 with SPACE parity (CMSPAR, parity bit=0)")
        print("dry-run:",not args.send)
        print()

        # Require runs of 90,21,22, then A3. With ODD RX the scan bytes are parity-OK.
        stages=[0x90,0x21,0x22]
        stage=0; count=0; carry=b""
        deadline=time.monotonic()+args.timeout
        found=False
        while time.monotonic()<deadline:
            r,_,_=select.select([fd],[],[],0.2)
            if not r: continue
            try: raw=os.read(fd,4096)
            except BlockingIOError: continue
            items,carry=parmrk_items(raw,carry)
            for ok,b in items:
                if not ok: continue
                if stage<3:
                    want=stages[stage]
                    if b==want:
                        count+=1
                        if count>=5:
                            print(f"  matched {want:02X} x5")
                            stage+=1; count=0
                    elif b!=want:
                        # keep stage, restart only this run
                        count=0
                elif b==0xA3:
                    print("  first parity-OK A3 seen")
                    found=True
                    break
            if found: break

        if not found:
            print("Scan sequence not seen; NOTHING SENT.")
            return 2

        if not args.send:
            print("DRY RUN: would send exactly one byte 06 with SPACE parity.")
            return 0

        # Switch only for the one transmitted byte.
        set_space(fd)
        os.write(fd,b"\x06")
        termios.tcdrain(fd)
        print("  SENT exactly one byte: 06 (SPACE parity)")
        # Return to odd-parity receive mode immediately.
        set_rx_odd(fd)

        print(f"Listening {args.listen:.1f} s for CRC-valid 10->AA / 0100 ...")
        end=time.monotonic()+args.listen
        carry=b""; logical=bytearray(); t0=time.monotonic()
        while time.monotonic()<end:
            r,_,_=select.select([fd],[],[],0.1)
            if not r: continue
            try: raw=os.read(fd,4096)
            except BlockingIOError: continue
            items,carry=parmrk_items(raw,carry)
            # Both parity classes belong to the logical byte stream.
            for ok,b in items:
                logical.append(b)
            f=valid_10aa_0100(logical)
            if f:
                dt=(time.monotonic()-t0)*1000
                print(f"*** SUCCESS at +{dt:.1f} ms: {f.hex()} ***")
                return 0
            if len(logical)>4096: del logical[:-1024]
        print("No CRC-valid 10->AA / 0100 seen.")
        return 1
    finally:
        os.close(fd)

if __name__=="__main__":
    raise SystemExit(main())
