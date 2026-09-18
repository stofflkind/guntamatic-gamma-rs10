#!/usr/bin/env python3

import argparse
import time
from collections import Counter

VID = 0x0403
PID = 0x6001
SERIAL = "YOUR_FTDI_SERIAL"

BAUD = 9600
SAMPLE_RATE = BAUD * 16
DURATION = 2.0

parser = argparse.ArgumentParser(
    description="Capture raw Gamma/RS10 bus samples with an FT232R."
)
parser.add_argument(
    "output",
    help="Output file for raw samples",
)
args = parser.parse_args()

import ftdi1

ctx = ftdi1.new()

if ctx is None:
    raise RuntimeError("ftdi_new() fehlgeschlagen")

data = bytearray()

try:
    rc = ftdi1.usb_open_desc(ctx, VID, PID, None, SERIAL)

    if rc < 0:
        raise RuntimeError(
            "FT232R öffnen fehlgeschlagen: "
            + str(ftdi1.get_error_string(ctx))
        )

    print("FT232R geöffnet")

    # Alle acht Datenleitungen INPUT
    rc = ftdi1.set_bitmode(
        ctx,
        0x00,
        ftdi1.BITMODE_BITBANG
    )

    if rc < 0:
        raise RuntimeError(
            "Bit-Bang-Modus fehlgeschlagen: "
            + str(ftdi1.get_error_string(ctx))
        )

    rc = ftdi1.set_baudrate(ctx, BAUD)

    if rc < 0:
        raise RuntimeError(
            "Baudrate fehlgeschlagen: "
            + str(ftdi1.get_error_string(ctx))
        )

    print(f"Bit-Bang Baudrate : {BAUD}")
    print(f"Soll-Samplerate   : {SAMPLE_RATE} Samples/s")
    print(f"Sample-Abstand    : {1_000_000/SAMPLE_RATE:.3f} us")
    print(f"Capture-Dauer     : {DURATION:.1f} s")
    print()
    print("Capture läuft ...")

    start = time.monotonic()

    while time.monotonic() - start < DURATION:

        rc, buf = ftdi1.read_data(ctx)

        if rc < 0:
            raise RuntimeError(
                "read_data fehlgeschlagen: "
                + str(ftdi1.get_error_string(ctx))
            )

        if buf:
            data.extend(buf)

    elapsed = time.monotonic() - start

finally:

    try:
        ftdi1.set_bitmode(
            ctx,
            0x00,
            ftdi1.BITMODE_RESET
        )
    except Exception:
        pass

    try:
        ftdi1.usb_close(ctx)
    except Exception:
        pass

    ftdi1.free(ctx)


print()
print("Capture beendet.")
print()
print(f"Laufzeit             : {elapsed:.3f} s")
print(f"Samples empfangen    : {len(data)}")

if elapsed:
    print(
        f"Samples pro Sekunde  : "
        f"{len(data)/elapsed:.0f}"
    )

expected = SAMPLE_RATE * elapsed

print(f"Samples erwartet     : {expected:.0f}")

if expected:
    print(
        f"Verhältnis Ist/Soll  : "
        f"{100*len(data)/expected:.1f} %"
    )

print()

# Verteilung der kompletten D0-D7 Samples
counts = Counter(data)

print("Häufigste Pinzustände:")

for value, count in counts.most_common(10):
    print(
        f"  0x{value:02x} : "
        f"{count:8d} "
        f"({100*count/len(data):6.2f} %)"
    )

# RXD = D1 extrahieren
rx = [(x >> 1) & 1 for x in data]

ones = sum(rx)
zeros = len(rx) - ones

print()
print("RXD / D1:")
print(f"  LOW  : {zeros}")
print(f"  HIGH : {ones}")

# Flanken zählen
edges = 0

for a, b in zip(rx, rx[1:]):
    if a != b:
        edges += 1

print(f"  Flanken: {edges}")

# Rohsamples speichern
filename = args.output

with open(filename, "wb") as f:
    f.write(data)

print()
print(f"Rohdaten gespeichert: {filename}")
print("FT232R wieder auf normalen UART-Modus gesetzt.")
