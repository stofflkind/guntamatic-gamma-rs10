#!/usr/bin/env python3

from pathlib import Path

import argparse

parser = argparse.ArgumentParser(
    description="Compare TYPE 8001 between two FT232R captures."
)
parser.add_argument("capture_a", type=Path)
parser.add_argument("capture_b", type=Path)
args = parser.parse_args()

FILES = [args.capture_a, args.capture_b]

SAMPLE_RATE = 307200
BAUD = 9600
SPB = SAMPLE_RATE / BAUD
D1_MASK = 0x02


def crc16_kermit(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xffff


def level(samples, pos):
    i = int(round(pos))
    return 1 if samples[i] & D1_MASK else 0


def decode(samples):
    frames = []
    i = 1

    while i + int(11 * SPB) < len(samples):
        if level(samples, i - 1) == 1 and level(samples, i) == 0:
            start = i

            value = 0
            for bit in range(8):
                if level(samples, start + (1.5 + bit) * SPB):
                    value |= 1 << bit

            bit9 = level(samples, start + 9.5 * SPB)
            stop = level(samples, start + 10.5 * SPB)

            if stop == 1:
                frames.append((value, bit9))
                i = int(start + 11 * SPB)
                continue
        i += 1

    return frames


def find_8001(path):
    frames = decode(path.read_bytes())
    result = []

    for i in range(len(frames) - 4):
        if frames[i][0] != 0x82:
            continue

        ll = frames[i + 3][0]

        if ll != 0x80:
            continue

        length = ll + 8
        if i + length > len(frames):
            continue

        raw = bytes(x[0] for x in frames[i:i + length])

        if raw[-1] != 0x03:
            continue

        stored = int.from_bytes(raw[-3:-1], "little")
        calculated = crc16_kermit(raw[1:-3])

        if stored == calculated and raw[4] == 0x01:
            result.append(raw)

    return result


a = find_8001(FILES[0])
b = find_8001(FILES[1])

print(f"22.0 °C: {len(a)} x TYPE 8001")
print(f"22.5 °C: {len(b)} x TYPE 8001")

if len(b) < 2:
    raise SystemExit("Zu wenige 8001 im 22.5-Mitschnitt")

x = b[0]
y = b[1]

print()
print("Unterschiede:")

for pos, (old, new) in enumerate(zip(x, y)):
    if old != new:
        print(f"Byte {pos:3d}: {old:02X} -> {new:02X}")
