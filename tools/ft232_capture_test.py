#!/usr/bin/env python3
import argparse
import time
from collections import Counter

VID = 0x0403
PID = 0x6001
SERIAL = "YOUR_FTDI_SERIAL"

# Der RS485-Bus läuft mit 9600 Baud.
# Beim FT232R ergibt der Bit-Bang-Modus daraus nominell
# 16 Samples pro UART-Bit.
BAUD = 9600
SAMPLE_RATE = BAUD * 16
DURATION = 2.0
BUFFER_SIZE = 4096

parser = argparse.ArgumentParser(
    description="Test FT232R raw capture on the Gamma/RS10 bus."
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
elapsed = 0.0

try:
    rc = ftdi1.usb_open_desc(
        ctx,
        VID,
        PID,
        None,
        SERIAL
    )

    if rc < 0:
        raise RuntimeError(
            "FT232R öffnen fehlgeschlagen: "
            + str(ftdi1.get_error_string(ctx))
        )

    print("FT232R geöffnet")

    # Alle D0..D7 als Eingang.
    # Damit treiben wir keine dieser Leitungen aktiv.
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
    print(
        f"Sample-Abstand    : "
        f"{1_000_000 / SAMPLE_RATE:.3f} us"
    )
    print(f"Capture-Dauer     : {DURATION:.1f} s")
    print(f"USB-Puffer        : {BUFFER_SIZE} Bytes")
    print()
    print("Capture läuft ...")

    start = time.monotonic()

    while time.monotonic() - start < DURATION:

        buf = bytearray(BUFFER_SIZE)

        rc = ftdi1.read_data(ctx, buf)

        if rc < 0:
            raise RuntimeError(
                "read_data fehlgeschlagen: "
                + str(ftdi1.get_error_string(ctx))
            )

        if rc > 0:
            data.extend(buf[:rc])

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

    print("FT232R wieder auf normalen UART-Modus gesetzt.")


print()
print("Capture beendet.")
print()

print(f"Laufzeit             : {elapsed:.3f} s")
print(f"Samples empfangen    : {len(data)}")

if elapsed > 0:

    actual_rate = len(data) / elapsed

    print(
        f"Samples pro Sekunde  : "
        f"{actual_rate:.0f}"
    )

    expected = SAMPLE_RATE * elapsed

    print(
        f"Samples erwartet     : "
        f"{expected:.0f}"
    )

    if expected > 0:

        print(
            f"Verhältnis Ist/Soll  : "
            f"{100 * len(data) / expected:.1f} %"
        )


if data:

    print()
    print("Häufigste Pinzustände:")

    counts = Counter(data)

    for value, count in counts.most_common(10):

        print(
            f"  0x{value:02x} : "
            f"{count:8d} "
            f"({100 * count / len(data):6.2f} %)"
        )

    # ------------------------------------------------
    # D1 = RXD extrahieren
    # ------------------------------------------------

    rx = [
        (sample >> 1) & 1
        for sample in data
    ]

    ones = sum(rx)
    zeros = len(rx) - ones

    print()
    print("RXD / D1:")
    print(f"  LOW    : {zeros}")
    print(f"  HIGH   : {ones}")

    # ------------------------------------------------
    # Flanken zählen
    # ------------------------------------------------

    edges = 0

    for a, b in zip(rx, rx[1:]):

        if a != b:
            edges += 1

    print(f"  Flanken : {edges}")

    # ------------------------------------------------
    # Rohdaten speichern
    # ------------------------------------------------

    filename = args.output

    with open(filename, "wb") as f:
        f.write(data)

    print()
    print(
        f"Rohdaten gespeichert: "
        f"{filename}"
    )

else:

    print()
    print("WARNUNG: Keine Samples empfangen.")
