#!/usr/bin/env python3

from pathlib import Path

CAPTURE_FILE = Path.home() / "ft232_capture.bin"

SAMPLE_RATE = 307200.0
BAUD = 9600.0
SAMPLES_PER_BIT = SAMPLE_RATE / BAUD

RXD_MASK = 0x02

# Ein größerer Abstand als dieser Wert wird zusätzlich als Pause markiert.
GAP_MS = 5.0


def level(samples, pos):
    """Logischen Zustand von RXD/D1 an Sampleposition pos liefern."""
    if pos < 0 or pos >= len(samples):
        return None
    return 1 if (samples[pos] & RXD_MASK) else 0


def sample_bit(samples, start, bit_position):
    """
    Bit in der Mitte seiner Bitzeit abtasten.

    bit_position:
        0  = Startbit
        1  = D0
        ...
        8  = D7
        9  = Bit 9
        10 = Stopbit
    """
    pos = int(round(start + (bit_position + 0.5) * SAMPLES_PER_BIT))

    if pos >= len(samples):
        return None

    return level(samples, pos)


def parity_class(value, bit9):
    """
    Nur mathematische Klassifikation des neunten Bits.

    Das bedeutet ausdrücklich NICHT, dass Bit9 bereits als
    klassisches UART-Paritätsbit interpretiert wird.
    """
    ones = bin(value).count("1")

    even_bit = ones & 1
    odd_bit = 1 - even_bit

    if bit9 == even_bit:
        return "EVEN"

    if bit9 == odd_bit:
        return "ODD"

    return "?"


def decode_frame(samples, start):
    """Versucht an start ein 8 Datenbit + Bit9 + Stopbit Frame zu lesen."""

    # Startbit muss LOW sein.
    if sample_bit(samples, start, 0) != 0:
        return None

    # 8 Datenbits LSB first.
    value = 0

    for bit in range(8):
        v = sample_bit(samples, start, bit + 1)

        if v is None:
            return None

        if v:
            value |= 1 << bit

    bit9 = sample_bit(samples, start, 9)
    stop = sample_bit(samples, start, 10)

    if bit9 is None or stop is None:
        return None

    # Stopbit muss HIGH sein.
    if stop != 1:
        return None

    return {
        "sample": start,
        "byte": value,
        "bit9": bit9,
        "class": parity_class(value, bit9),
    }


def find_frames(samples):
    """
    Frames anhand von HIGH->LOW-Flanken suchen.

    Nach einem gültigen Frame wird zunächst über dessen komplette
    Länge gesprungen. Danach suchen wir wieder die nächste fallende
    Flanke.
    """

    frames = []

    i = 1
    frame_samples = int(round(11 * SAMPLES_PER_BIT))

    while i < len(samples) - frame_samples:

        previous = level(samples, i - 1)
        current = level(samples, i)

        if previous == 1 and current == 0:

            frame = decode_frame(samples, i)

            if frame is not None:
                frames.append(frame)

                i += frame_samples
                continue

        i += 1

    return frames


def ms_from_samples(count):
    return count * 1000.0 / SAMPLE_RATE


def seconds_from_samples(count):
    return count / SAMPLE_RATE


def print_scan_summary(frames):
    print()
    print("Bit9=1 Marker")
    print("=============")
    print()

    marker_number = 0
    previous_marker = None

    for frame in frames:

        if frame["bit9"] != 1:
            continue

        if previous_marker is None:
            gap_text = "-"
        else:
            gap = frame["sample"] - previous_marker["sample"]
            gap_text = f"{ms_from_samples(gap):8.3f} ms"

        print(
            f"{marker_number:4d}  "
            f"t={seconds_from_samples(frame['sample']):9.6f} s  "
            f"{frame['byte']:02X}/1  "
            f"{frame['class']:4s}  "
            f"Abstand={gap_text}"
        )

        previous_marker = frame
        marker_number += 1


def split_blocks(frames):
    """
    Ein Bit9=1-Zeichen startet einen neuen Block.

    Frames vor dem ersten Marker werden als eigener PREAMBLE-Block
    behandelt.
    """

    blocks = []
    current = []

    for frame in frames:

        if frame["bit9"] == 1:

            if current:
                blocks.append(current)

            current = [frame]

        else:
            current.append(frame)

    if current:
        blocks.append(current)

    return blocks


def block_signature(block):
    """
    Kompakte Signatur eines Blocks.

    Byte und Bit9 werden berücksichtigt.
    """
    return tuple((f["byte"], f["bit9"]) for f in block)


def print_blocks(blocks):
    print()
    print("Telegramm-Blöcke")
    print("================")
    print()

    previous_block = None

    for nr, block in enumerate(blocks):

        if not block:
            continue

        first = block[0]
        last = block[-1]

        start_time = seconds_from_samples(first["sample"])

        if previous_block:
            previous_start = previous_block[0]["sample"]
            start_gap_ms = ms_from_samples(
                first["sample"] - previous_start
            )
        else:
            start_gap_ms = None

        duration_ms = ms_from_samples(
            last["sample"] - first["sample"]
        )

        marker = (
            f"{first['byte']:02X}/{first['bit9']}"
            if first["bit9"] == 1
            else "PREAMBLE"
        )

        print("-" * 72)

        print(
            f"Block {nr:03d}   "
            f"Marker={marker}   "
            f"Frames={len(block)}"
        )

        print(
            f"Start: {start_time:.6f} s   "
            f"Dauer: {duration_ms:.3f} ms"
        )

        if start_gap_ms is not None:
            print(
                f"Abstand zum vorherigen Blockstart: "
                f"{start_gap_ms:.3f} ms"
            )

        print()

        line = []

        for frame in block:
            line.append(
                f"{frame['byte']:02X}/{frame['bit9']}"
            )

            if len(line) == 12:
                print("  " + " ".join(line))
                line = []

        if line:
            print("  " + " ".join(line))

        print()

        # Abstände innerhalb des Blocks
        if len(block) > 1:

            gaps = []

            for a, b in zip(block, block[1:]):
                gap = b["sample"] - a["sample"]

                if ms_from_samples(gap) >= GAP_MS:
                    gaps.append(
                        (
                            a["byte"],
                            b["byte"],
                            ms_from_samples(gap),
                        )
                    )

            if gaps:
                print(f"  Pausen >= {GAP_MS:.1f} ms:")

                for a, b, gap_ms in gaps:
                    print(
                        f"    {a:02X} -> {b:02X}: "
                        f"{gap_ms:.3f} ms"
                    )

                print()

        previous_block = block


def print_repetitions(blocks):
    print()
    print("Wiederholte Blockstrukturen")
    print("===========================")
    print()

    signatures = {}

    for nr, block in enumerate(blocks):

        if not block:
            continue

        sig = block_signature(block)

        signatures.setdefault(sig, []).append(nr)

    repetitions = [
        (sig, numbers)
        for sig, numbers in signatures.items()
        if len(numbers) > 1
    ]

    repetitions.sort(
        key=lambda item: (-len(item[1]), item[1][0])
    )

    if not repetitions:
        print("Keine exakt identischen Blöcke gefunden.")
        return

    for sig, numbers in repetitions:

        marker = sig[0]

        print(
            f"{len(numbers):3d}x identisch   "
            f"Marker={marker[0]:02X}/{marker[1]}   "
            f"Frames={len(sig):3d}   "
            f"Blöcke={','.join(str(n) for n in numbers)}"
        )


def main():

    print("FT232R Gamma/RS10 Telegramm-Analyse")
    print("====================================")
    print()

    if not CAPTURE_FILE.exists():
        print(f"Datei nicht gefunden: {CAPTURE_FILE}")
        return

    samples = CAPTURE_FILE.read_bytes()

    print(f"Capture-Datei     : {CAPTURE_FILE}")
    print(f"Samples           : {len(samples)}")
    print(f"Samplerate        : {SAMPLE_RATE:.0f} Samples/s")
    print(f"Baudrate          : {BAUD:.0f}")
    print(f"Samples/Bit       : {SAMPLES_PER_BIT:.1f}")

    frames = find_frames(samples)

    print(f"Erkannte Frames   : {len(frames)}")

    marker_count = sum(
        1 for frame in frames
        if frame["bit9"] == 1
    )

    print(f"Frames Bit9=1     : {marker_count}")
    print(f"Frames Bit9=0     : {len(frames) - marker_count}")

    blocks = split_blocks(frames)

    print(f"Telegramm-Blöcke  : {len(blocks)}")

    print_scan_summary(frames)
    print_blocks(blocks)
    print_repetitions(blocks)


if __name__ == "__main__":
    main()
