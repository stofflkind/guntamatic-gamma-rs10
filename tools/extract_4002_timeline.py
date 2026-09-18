#!/usr/bin/env python3

import re
import sys
from datetime import datetime
from pathlib import Path

LINE_RE = re.compile(r"^(\S+)\s+([0-9a-fA-F]+)$")

START = b"\x82"


def crc16_kermit(data: bytes) -> int:
    crc = 0x0000

    for byte in data:
        crc ^= byte

        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1

    return crc & 0xFFFF


def decode_interleaved_frame(raw: bytes, start: int):
    """
    Try to decode an FF-interleaved Gamma frame beginning at raw[start].

    Logical stream:
        82 10 20 40 02 ...

    Physical capture:
        82 ff 10 ff 20 ff 40 ff 02 ff ...
    """

    if raw[start] != 0x82:
        return None

    # Need header through LL.
    if start + 8 > len(raw):
        return None

    # First four logical bytes, assuming FF separators.
    logical = []

    pos = start

    while len(logical) < 4:
        if pos >= len(raw):
            return None

        logical.append(raw[pos])

        if pos + 1 >= len(raw) or raw[pos + 1] != 0xFF:
            return None

        pos += 2

    ll = logical[3]
    logical_length = ll + 8
    physical_length = logical_length * 2

    if start + physical_length > len(raw):
        return None

    block = raw[start:start + physical_length]

    if not all(block[i] == 0xFF for i in range(1, len(block), 2)):
        return None

    frame = bytes(block[i] for i in range(0, len(block), 2))

    if len(frame) != logical_length:
        return None

    if frame[0] != 0x82 or frame[-1] != 0x03:
        return None

    expected = frame[-3] | (frame[-2] << 8)
    actual = crc16_kermit(frame[1:-3])

    if actual != expected:
        return None

    return frame


def main():
    if len(sys.argv) != 4:
        print(
            f"Usage: {sys.argv[0]} RAW_LOG START END\n"
            "Example:\n"
            f"  {sys.argv[0]} /tmp/guntamatic-rs485.raw.log "
            "2026-09-17T20:45:00+02:00 2026-09-17T22:30:00+02:00"
        )
        raise SystemExit(2)

    path = Path(sys.argv[1])
    start_time = datetime.fromisoformat(sys.argv[2])
    end_time = datetime.fromisoformat(sys.argv[3])

    chunks = []
    offsets = []
    total = 0

    for line in path.read_text(
        encoding="ascii", errors="ignore"
    ).splitlines():

        match = LINE_RE.match(line.strip())

        if not match:
            continue

        timestamp_text, hexdata = match.groups()

        try:
            timestamp = datetime.fromisoformat(timestamp_text)
        except ValueError:
            continue

        if not (start_time <= timestamp <= end_time):
            continue

        try:
            data = bytes.fromhex(hexdata)
        except ValueError:
            continue

        offsets.append((total, timestamp))
        chunks.append(data)
        total += len(data)

    raw = b"".join(chunks)

    if not raw:
        print("No raw data found.")
        raise SystemExit(1)

    def timestamp_for_offset(offset):
        result = offsets[0][1]

        for position, timestamp in offsets:
            if position > offset:
                break
            result = timestamp

        return result

    results = []

    pos = 0

    while pos < len(raw):

        if raw[pos] != START[0]:
            pos += 1
            continue

        frame = decode_interleaved_frame(raw, pos)

        if frame is None:
            pos += 1
            continue

        # TYPE = LL + first content byte
        msg_type = f"{frame[3]:02x}{frame[4]:02x}"

        if msg_type == "4002":

            # P08 = content[7] = complete frame byte 11
            p08 = frame[11]
            temperature = p08 / 2.0

            timestamp = timestamp_for_offset(pos)

            results.append(
                (timestamp, temperature, p08)
            )

        pos += len(frame) * 2

    if not results:
        print("No CRC-valid TYPE 4002 frames found.")
        return

    print("Timestamp                         DHW       P08")
    print("------------------------------------------------")

    for timestamp, temperature, p08 in results:
        print(
            f"{timestamp.isoformat():32s} "
            f"{temperature:5.1f} °C  "
            f"0x{p08:02X}"
        )

    maximum = max(results, key=lambda x: x[1])

    print()
    print(
        f"MAX: {maximum[1]:.1f} °C "
        f"at {maximum[0].isoformat()} "
        f"(P08=0x{maximum[2]:02X})"
    )


if __name__ == "__main__":
    main()
