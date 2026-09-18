#!/usr/bin/env python3
"""
Passive Gamma/RS10 parity probe.

Physical RS10 CONNECTED. This script NEVER writes to the serial port.
It configures 9600 baud, 8 data bits, EVEN parity, 1 stop bit, enables
INPCK+PARMRK, and prints Linux PARMRK-decoded bytes:

  OK  xx       byte received with selected parity
  ERR xx       byte received with parity/framing error
  FF           valid literal 0xff (encoded by Linux as ff ff)

Run first with --parity even, then optionally --parity odd.
"""
import argparse, os, sys, termios, time, select

def configure(fd, parity):
    a = termios.tcgetattr(fd)
    # input: parity checking + marking; don't ignore errors, don't strip bit 8
    a[0] = termios.INPCK | termios.PARMRK
    a[1] = 0
    a[2] = termios.CLOCAL | termios.CREAD | termios.CS8 | termios.PARENB
    if parity == "odd":
        a[2] |= termios.PARODD
    a[2] &= ~termios.CSTOPB
    a[3] = 0
    a[4] = termios.B9600
    a[5] = termios.B9600
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIFLUSH)

def decode_parmrk(buf, carry=b""):
    d = carry + buf
    out=[]
    i=0
    while i < len(d):
        if d[i] != 0xff:
            out.append(("OK", d[i])); i+=1; continue
        if i+1 >= len(d): break
        if d[i+1] == 0xff:
            out.append(("OK", 0xff)); i+=2; continue
        if d[i+1] == 0x00:
            if i+2 >= len(d): break
            out.append(("ERR", d[i+2])); i+=3; continue
        # Unexpected form: retain literal FF rather than inventing an error.
        out.append(("OK",0xff)); i+=1
    return out, d[i:]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--parity", choices=["even","odd"], default="even")
    ap.add_argument("--seconds", type=float, default=15.0)
    args=ap.parse_args()

    flags=os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK
    fd=os.open(args.port, flags)
    try:
        configure(fd,args.parity)
        print("RS10 passive parity probe")
        print("port   :",args.port)
        print("format : 9600 8%s1 + INPCK + PARMRK" % ("E" if args.parity=="even" else "O"))
        print("TX     : NONE (opened read-only)")
        print("Legend : '.' parity OK, '!' parity/framing error")
        print()
        end=time.monotonic()+args.seconds
        carry=b""
        line=[]
        last=time.monotonic()
        while time.monotonic()<end:
            r,_,_=select.select([fd],[],[],0.1)
            if not r: continue
            try: b=os.read(fd,4096)
            except BlockingIOError: continue
            if not b: continue
            items,carry=decode_parmrk(b,carry)
            now=time.monotonic()
            for kind,val in items:
                line.append(("!" if kind=="ERR" else ".")+f"{val:02X}")
            if len(line)>=32 or now-last>0.25:
                print(" ".join(line))
                line=[]; last=now
        if line: print(" ".join(line))
        if carry: print("partial PARMRK tail:",carry.hex())
    finally:
        os.close(fd)

if __name__=="__main__":
    main()
