#!/usr/bin/env python3
"""
Analyze Gamma/RS10 raw capture timing.

Input format: lines like
  2026-09-14 ... +00012.580736s a306

This measures HOST-READ chunk timing, not true wire-level byte timing.
That distinction is important with FTDI latency/buffering.

It reports:
- successful selector-3 presence events (chunk containing A3 06)
- time from A3/06 chunk to first chunk containing 10->AA / 0100 start
- time to 90/06 and RS10 23->10 requests
- scan-token inter-read gaps
- normal cycle period between A3/06 events
- evidence of FTDI ~16 ms chunk quantization
"""

import argparse, re, statistics
from pathlib import Path

LINE_RE = re.compile(r"\+([0-9.]+)s\s+([0-9a-fA-F]+)\s*$")

def load(path):
    e=[]
    for line in Path(path).read_text(errors="replace").splitlines():
        m=LINE_RE.search(line)
        if m:
            e.append((float(m.group(1)), bytes.fromhex(m.group(2)), line))
    return e

def ms(x): return x*1000.0

def median(xs):
    return statistics.median(xs) if xs else None

def fmt(v):
    return "n/a" if v is None else f"{v:.3f} ms"

def first_after(entries, idx, pred, limit_s=1.0):
    t0=entries[idx][0]
    for j in range(idx+1, len(entries)):
        if entries[j][0]-t0 > limit_s: break
        if pred(entries[j][1]):
            return j
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("log", nargs="?", default="rs10-startup-physical.log")
    args=ap.parse_args()
    E=load(args.log)
    if not E:
        raise SystemExit("No timestamped hex entries found.")

    print(f"file: {args.log}")
    print(f"timestamped read chunks: {len(E)}")
    print()
    print("NOTE: timestamps are when Linux/Python received a read chunk.")
    print("      They are NOT per-byte wire timestamps.")
    print()

    active=[i for i,(_,b,_) in enumerate(E) if b.find(b"\xa3\x06") >= 0]
    print(f"A3+06 chunks: {len(active)}")
    event_rows=[]
    for n,i in enumerate(active,1):
        t0,b,_=E[i]
        j10=first_after(E,i,lambda x: b"\xff\xa3\xff\x82\xff\x10\xff\xaa\xff\x01" in x
                                  or x.startswith(bytes.fromhex("8210aa01")),0.2)
        j90=first_after(E,i,lambda x: x==b"\x90\x06" or b"\x90\x06" in x,0.3)
        j23=first_after(E,i,lambda x: b"\xff\x90\xff\x82\xff\x23\xff\x10" in x
                                  or x.startswith(bytes.fromhex("822310")),0.4)
        d10=ms(E[j10][0]-t0) if j10 is not None else None
        d90=ms(E[j90][0]-t0) if j90 is not None else None
        d23=ms(E[j23][0]-t0) if j23 is not None else None
        event_rows.append((t0,d10,d90,d23))
        print(f"event {n}: t={t0:.6f}s  A3/06->10AA {fmt(d10)}"
              f"  ->90/06 {fmt(d90)}  ->23->10 {fmt(d23)}")

    if len(active)>=2:
        periods=[ms(E[b][0]-E[a][0]) for a,b in zip(active,active[1:])]
        print()
        print("A3+06 event periods:")
        print("  " + ", ".join(f"{x:.3f} ms" for x in periods))
        if len(periods)>1:
            normal=periods[1:] if periods[0] > 8000 else periods
            print(f"  median normal period: {median(normal):.3f} ms")

    # Scan-token timestamp gaps: isolated one-byte scan chunks.
    scan_values={0x90,0x21,0x22,0xA3,0x11,0x12,0x93,0x14,0x95,0x96,
                 0x17,0x18,0x99,0x9A,0x1B,0x9C,0x1D,0x1E,0x9F}
    scan_times=[t for t,b,_ in E if len(b)==1 and b[0] in scan_values]
    gaps=[ms(b-a) for a,b in zip(scan_times,scan_times[1:])
          if 0 < b-a < 0.1]
    print()
    print(f"isolated scan-token gaps sampled: {len(gaps)}")
    if gaps:
        print(f"  median: {median(gaps):.3f} ms")
        # buckets to expose USB/read quantization
        buckets={}
        for g in gaps:
            k=round(g)
            buckets[k]=buckets.get(k,0)+1
        top=sorted(buckets.items(), key=lambda kv:(-kv[1],kv[0]))[:8]
        print("  most common rounded gaps: " +
              ", ".join(f"{k} ms ({v}x)" for k,v in top))

    # Consecutive read-chunk gaps across whole capture.
    allg=[ms(E[i+1][0]-E[i][0]) for i in range(len(E)-1)
          if 0 < E[i+1][0]-E[i][0] < 0.05]
    buckets={}
    for g in allg:
        k=round(g,1)
        buckets[k]=buckets.get(k,0)+1
    top=sorted(buckets.items(), key=lambda kv:(-kv[1],kv[0]))[:12]
    print()
    print("Most common sub-50ms HOST read-chunk gaps:")
    print("  " + ", ".join(f"{k:.1f} ms ({v}x)" for k,v in top))

    print()
    print("Interpretation:")
    print("  If ~15-16 ms and ~31-32 ms dominate, the capture is strongly")
    print("  quantized by FTDI/USB buffering. In that case A3->06 cannot be")
    print("  recovered as true wire timing from this log, especially when A3")
    print("  and 06 are in the SAME read chunk.")
    print("  For true response-window timing use a logic analyzer/scope, or")
    print("  a capture path that timestamps UART events below USB-host latency.")

if __name__=="__main__":
    main()
