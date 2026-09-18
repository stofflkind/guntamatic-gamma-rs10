#!/usr/bin/env python3

from pathlib import Path
import argparse


SAMPLE_RATE = 307200
BAUD = 9600
SPB = SAMPLE_RATE / BAUD
D1_MASK = 0x02


def crc16_kermit(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else (crc >> 1)
    return crc & 0xffff


def level(samples, pos):
    i = int(round(pos))
    if i < 0 or i >= len(samples):
        return 1
    return 1 if (samples[i] & D1_MASK) else 0


def decode_frames(samples):
    frames = []
    i = 1
    n = len(samples)

    while i + int(11 * SPB) < n:
        # Startflanke HIGH -> LOW
        if level(samples, i - 1) == 1 and level(samples, i) == 0:

            start = i

            # Startbit prüfen
            if level(samples, start + 0.5 * SPB) != 0:
                i += 1
                continue

            value = 0
            for bit in range(8):
                if level(samples, start + (1.5 + bit) * SPB):
                    value |= 1 << bit

            bit9 = level(samples, start + 9.5 * SPB)
            stop = level(samples, start + 10.5 * SPB)

            if stop == 1:
                frames.append((start, value, bit9))
                i = int(start + 11 * SPB)
                continue

        i += 1

    return frames


def main():
    parser = argparse.ArgumentParser(description="FT232R-Rohcapture in CRC-gueltige Gamma-Frames umwandeln")
    parser.add_argument("capture", type=Path, help="FT232R-Rohcapture (.bin)")
    args = parser.parse_args()

    capture = args.capture.expanduser()
    samples = capture.read_bytes()
    frames = decode_frames(samples)

    print("FT232R CRC-gültige Gamma-Frames")
    print("================================")
    print(f"9-Bit-Frames erkannt: {len(frames)}")
    print()

    found = []

    for i, (sample_pos, value, bit9) in enumerate(frames):

        if value != 0x82:
            continue

        # Mindestens Header 82 src dst LL
        if i + 3 >= len(frames):
            continue

        ll = frames[i + 3][1]
        total_length = ll + 8

        if i + total_length > len(frames):
            continue

        candidate = bytes(
            frames[j][1]
            for j in range(i, i + total_length)
        )

        if candidate[0] != 0x82:
            continue

        if candidate[-1] != 0x03:
            continue

        stored = int.from_bytes(candidate[-3:-1], "little")
        calculated = crc16_kermit(candidate[1:-3])

        if stored != calculated:
            continue

        src = candidate[1]
        dst = candidate[2]
        content = candidate[4:5 + ll]

        if content:
            msg_type = f"{ll:02X}{content[0]:02X}"
        else:
            msg_type = f"{ll:02X}??"

        t = sample_pos / SAMPLE_RATE

        found.append((t, src, dst, msg_type, candidate))

    output = Path.home() / "ft232r-analyzer/output/ft232_gamma_frames.bin"
    output.write_bytes(b"".join(raw for _, _, _, _, raw in found))
    print(f"Gamma-Byte-Stream gespeichert: {output}")

    for nr, (t, src, dst, msg_type, raw) in enumerate(found, 1):
        print(
            f"{nr:3d}  "
            f"t={t:8.3f}s  "
            f"{src:02X}->{dst:02X}  "
            f"TYPE={msg_type}  "
            f"LEN={len(raw):3d}  "
            f"CRC=OK"
        )
        print("     " + raw.hex(" ").upper())

    print()
    print(f"CRC-gültige Gamma-Frames: {len(found)}")

    types = {}
    for _, _, _, msg_type, _ in found:
        types[msg_type] = types.get(msg_type, 0) + 1

    if types:
        print()
        print("Telegrammtypen:")
        for msg_type, count in sorted(types.items()):
            print(f"  {msg_type}: {count}x")


if __name__ == "__main__":
    main()
