#!/usr/bin/env python3
"""
gamma_parser_v2.py

Read-only parser/analyzer for Gamma / Gamma RS10 RS485 traffic.

Current experimentally confirmed decoding (test system: Gamma RS10 +
Fischer/Guntamatic BIOSTAR 15):

  0905  Controller date/time (partially decoded)
  2004  P02 outside temperature, P17/P18 unknown, P32 Gamma-side boiler/flow temperature (likely)
  4002  P08 domestic hot-water actual temperature = raw/2 °C (confirmed)
  800E  Boiler weekly programme 1 (7 days x 3 intervals, confirmed)
  800F  Boiler weekly programme 2 (same confirmed structure)
  8010  Boiler weekly programme 3 (same confirmed structure)
  8012  Domestic hot-water weekly programme (times confirmed; slot setpoint semantic likely from manual)
  8014  RS10 parameter/configuration block (partially decoded: Reduziert, Kessel-PROG, Steilheit, Legionellen-WW, WW-PROG)
  010E  Request boiler weekly programme 1
  010F  Request boiler weekly programme 2
  0110  Request boiler weekly programme 3
  0112  Request domestic hot-water weekly programme
  0114  Request RS10 parameter/configuration block
  2806  P02 room actual temperature
        P04 active room setpoint
        P07 operating mode
        P10 domestic hot-water setpoint
        P11 manual DHW recharge state/command (direction-sensitive, likely)
        P37 day room setpoint
        P38 night room setpoint
        P39/P40/P41 timed-mode end minute/hour/weekday

The program is passive/read-only. It never writes to the RS485 bus.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional, TextIO

START_BYTE = 0x82
END_BYTE = 0x03

ADDRESS_NAMES = {
    0x23: "RS10#3",
    0x10: "controller?",
    0x20: "bus-node?",
    0xAA: "service/broadcast?",
}

OPERATING_MODES = {
    0x00: "automatic",
    0x03: "heating",
    0x04: "reduced",
    0x13: "party",
    0x14: "away",
    0x24: "vacation",
}

WEEKDAYS = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}


@dataclass(frozen=True)
class Frame:
    raw: bytes
    source: int
    destination: int
    length_byte: int
    message_type: str
    content: bytes
    crc_stored: int
    crc_calculated: int

    @property
    def crc_ok(self) -> bool:
        return self.crc_stored == self.crc_calculated


# ---------------------------------------------------------------------------
# Protocol primitives
# ---------------------------------------------------------------------------

def crc16_kermit(data: bytes) -> int:
    """CRC-16/KERMIT: reflected poly 0x8408, init 0x0000, xorout 0x0000."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF


def make_frame(buf: bytes) -> Optional[Frame]:
    """Build one frame from an already normalized byte sequence."""
    if len(buf) < 8 or buf[0] != START_BYTE or buf[-1] != END_BYTE:
        return None

    ll = buf[3]
    if len(buf) != ll + 8:
        return None

    # Layout: 82 | src | dst | LL | content (LL+1) | CRC lo | CRC hi | 03
    content = buf[4 : 5 + ll]
    stored = int.from_bytes(buf[-3:-1], "little")
    calculated = crc16_kermit(buf[1:-3])
    msg_type = f"{ll:02x}{content[0]:02x}" if content else f"{ll:02x}??"

    return Frame(
        raw=buf,
        source=buf[1],
        destination=buf[2],
        length_byte=ll,
        message_type=msg_type,
        content=content,
        crc_stored=stored,
        crc_calculated=calculated,
    )


def iter_frames(stream: bytes, accept_bad_crc: bool = False) -> Iterator[Frame]:
    """Extract frames using the length byte; payload 0x03 does not confuse framing."""
    pos = 0
    n = len(stream)
    while True:
        start = stream.find(bytes([START_BYTE]), pos)
        if start < 0 or start + 8 > n:
            return

        total = stream[start + 3] + 8
        end = start + total
        if end <= n:
            frame = make_frame(stream[start:end])
            if frame and (frame.crc_ok or accept_bad_crc):
                yield frame
                pos = end
                continue
        pos = start + 1


def count_valid_frames(stream: bytes, limit: Optional[int] = None) -> int:
    count = 0
    for _ in iter_frames(stream):
        count += 1
        if limit and count >= limit:
            break
    return count


# ---------------------------------------------------------------------------
# Input / normalization
# ---------------------------------------------------------------------------

def read_hexdump(path: Path) -> bytes:
    text = path.read_text(encoding="ascii", errors="ignore")
    hexchars = "".join(ch for ch in text if ch in "0123456789abcdefABCDEF")
    if len(hexchars) % 2:
        raise ValueError("Odd number of hexadecimal characters in input")
    return bytes.fromhex(hexchars)


def read_timestamped_hex_log(path: Path) -> bytes:
    """Read logs written as: ISO-8601-timestamp + space-separated hex frame.

    Example:
        2026-09-13T09:13:00.791+02:00 82 23 20 80 12 ... 03

    Only the byte tokens after the timestamp are used. Invalid/non-frame lines are
    ignored. Frames are concatenated so the normal frame extractor can process them.
    """
    out = bytearray()
    for line in path.read_text(encoding="ascii", errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        # Timestamped logger output has a non-hex first token and then byte tokens.
        byte_tokens = parts[1:]
        if not byte_tokens or byte_tokens[0].lower() != "82":
            continue
        try:
            frame = bytes(int(tok, 16) for tok in byte_tokens if len(tok) == 2)
        except ValueError:
            continue
        if frame and frame[0] == START_BYTE:
            out.extend(frame)
    return bytes(out)


def looks_like_timestamped_hex_log(sample: bytes) -> bool:
    text = sample.decode("ascii", errors="ignore")
    for line in text.splitlines()[:20]:
        parts = line.strip().split()
        if len(parts) >= 2 and "T" in parts[0] and parts[1].lower() == "82":
            return True
    return False


def read_input(path: Path, input_format: str) -> bytes:
    if input_format == "binary":
        return path.read_bytes()
    if input_format == "hex":
        return read_hexdump(path)
    if input_format == "log":
        return read_timestamped_hex_log(path)

    sample = path.read_bytes()[:8192]
    if looks_like_timestamped_hex_log(sample):
        return read_timestamped_hex_log(path)

    allowed = set(b"0123456789abcdefABCDEF \t\r\n")
    if sample and all(b in allowed for b in sample):
        return read_hexdump(path)
    return path.read_bytes()


def deinterleave_ff_separators(raw: bytes) -> bytes:
    """Remove capture-added 0xFF separator bytes while preserving genuine 0xFF data.

    The affected FTDI capture represents logical bytes as ``BYTE FF BYTE FF ...``.
    A genuine logical FF therefore appears as ``... FF FF FF ...`` on the physical
    stream (separator + data FF + separator).  Blind ``replace(FF, b"")`` destroys
    such payload bytes.

    This routine only deinterleaves runs that start at a plausible 0x82 frame and
    whose odd physical positions are all separator FF bytes.  Other bytes are kept
    unchanged so normal/non-interleaved captures remain recoverable by framing.
    """
    out = bytearray()
    pos = 0
    n = len(raw)
    while pos < n:
        start = raw.find(bytes([START_BYTE]), pos)
        if start < 0:
            out.extend(raw[pos:])
            break
        out.extend(raw[pos:start])

        # Need four logical header bytes at physical offsets 0,2,4,6.
        if start + 7 < n and all(raw[start + i] == 0xFF for i in (1, 3, 5)):
            ll = raw[start + 6]
            logical_total = ll + 8
            physical_total = logical_total * 2
            end = start + physical_total
            if end <= n and all(raw[start + i] == 0xFF for i in range(1, physical_total, 2)):
                candidate = bytes(raw[start + i] for i in range(0, physical_total, 2))
                frame = make_frame(candidate)
                if frame and frame.crc_ok:
                    out.extend(candidate)
                    pos = end
                    continue

        # Not a valid interleaved frame: preserve this byte and continue searching.
        out.append(raw[start])
        pos = start + 1
    return bytes(out)


def normalize_stream(raw: bytes, mode: str) -> tuple[bytes, str, dict]:
    if mode == "none":
        return raw, "none", {"raw_bytes": len(raw), "normalized_bytes": len(raw)}

    stripped = raw.replace(b"\xff", b"")
    deinterleaved = deinterleave_ff_separators(raw)

    if mode == "strip-ff":
        return stripped, "strip-ff", {
            "raw_bytes": len(raw),
            "normalized_bytes": len(stripped),
            "removed_ff": len(raw) - len(stripped),
            "warning": "legacy blind FF removal; genuine payload FF bytes are lost",
        }
    if mode == "deinterleave-ff":
        return deinterleaved, "deinterleave-ff", {
            "raw_bytes": len(raw),
            "normalized_bytes": len(deinterleaved),
            "removed_separator_bytes": len(raw) - len(deinterleaved),
        }

    # Auto: compare CRC-valid framing for all representations.  Prefer the
    # lossless deinterleaver on ties with legacy strip-ff.
    raw_score = count_valid_frames(raw, limit=2000)
    stripped_score = count_valid_frames(stripped, limit=2000)
    deinterleaved_score = count_valid_frames(deinterleaved, limit=2000)
    scores = {"none": raw_score, "strip-ff": stripped_score, "deinterleave-ff": deinterleaved_score}
    best_score = max(scores.values())
    if deinterleaved_score == best_score and best_score > 0:
        chosen, stream = "deinterleave-ff", deinterleaved
    elif raw_score == best_score:
        chosen, stream = "none", raw
    else:
        chosen, stream = "strip-ff", stripped
    return stream, chosen, {
        "raw_bytes": len(raw),
        "normalized_bytes": len(stream),
        "probe_raw_valid_frames": raw_score,
        "probe_stripped_valid_frames": stripped_score,
        "probe_deinterleaved_valid_frames": deinterleaved_score,
        "warning": ("legacy blind FF removal selected; genuine FF payloads may be lost" if chosen == "strip-ff" else None),
    }


# ---------------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------------

def bcd_byte(value: int) -> Optional[int]:
    hi, lo = (value >> 4) & 0xF, value & 0xF
    if hi > 9 or lo > 9:
        return None
    return hi * 10 + lo


def decode_0905(frame: Frame) -> dict:
    c = frame.content
    out = {"kind": "date_time", "confidence": "partial"}
    if len(c) < 10:
        out["error"] = "0905 content too short"
        return out

    sec = bcd_byte(c[2])
    minute = bcd_byte(c[3])
    hour = bcd_byte(c[4])
    day = bcd_byte(c[5])
    year2 = bcd_byte(c[7])
    weekday = bcd_byte(c[8])
    month = bcd_byte(c[9])

    out.update({
        "change_flag_raw": c[1],
        "second": sec,
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "year": 2000 + year2 if year2 is not None else None,
        "weekday": weekday,
        "packed_month_weekday_raw": c[6],
    })

    try:
        if None not in (year2, month, day, hour, minute, sec):
            out["timestamp"] = datetime(2000 + year2, month, day, hour, minute, sec).isoformat()
    except ValueError:
        out["timestamp_error"] = "invalid date/time fields"
    return out


def decode_2004(frame: Frame) -> dict:
    c = frame.content
    out = {"kind": "temperatures_status"}
    if len(c) < 33:
        out["error"] = "2004 content too short"
        return out

    out.update({
        "outside_temperature_c": c[1] / 2.0 - 52.0,
        "outside_temperature_status": "CONFIRMED",
        "p17_raw": c[16],
        "p17_status": "UNKNOWN",
        "p18_raw": c[17],
        "p18_status": "UNKNOWN",
        "gamma_boiler_flow_temperature_c": c[31] / 2.0,
        "gamma_boiler_flow_temperature_status": "LIKELY",
        "p33_raw": c[32],
        "p33_status": "UNKNOWN",
    })
    return out


def decode_4002(frame: Frame) -> dict:
    """Decode identified fields in cyclic 4002.

    P08 was confirmed on 2026-09-13 by direct simultaneous comparison with the
    RS10 information display: P08=0x6F -> 111/2 = 55.5 °C while the RS10 showed
    Warmwasser 55.5 °C. Historical 2016 data also shows a physically plausible
    DHW heating/cooling curve in this field.
    """
    c = frame.content
    out = {"kind": "gamma_extended_temperatures", "status": "PARTIALLY_DECODED"}
    if len(c) < 8:
        out["error"] = f"4002 content too short ({len(c)} bytes, expected >= 8)"
        return out
    out.update({
        "p08_raw": c[7],
        "hot_water_actual_c": c[7] / 2.0,
        "hot_water_actual_status": "CONFIRMED",
        "hot_water_actual_candidate_c": c[7] / 2.0,
        "hot_water_actual_candidate_status": "CONFIRMED",
    })
    return out


def decode_2806(frame: Frame) -> dict:
    c = frame.content
    out = {"kind": "rs10_state"}
    if len(c) < 41:
        out["error"] = f"2806 content too short ({len(c)} bytes, expected >= 41)"
        return out

    mode_raw = c[6]  # P7
    mode = OPERATING_MODES.get(mode_raw, f"unknown_0x{mode_raw:02x}")
    # P39/P40/P41 are mode-dependent:
    #   party/away: end minute, end hour, end weekday
    #   vacation:   end day, end month, two-digit end year
    minute = bcd_byte(c[38]) if mode_raw in (0x13, 0x14) else None
    hour = bcd_byte(c[39]) if mode_raw in (0x13, 0x14) else None
    weekday_raw = c[40] if mode_raw in (0x13, 0x14) else None
    vacation_day = bcd_byte(c[38]) if mode_raw == 0x24 else None
    vacation_month = bcd_byte(c[39]) if mode_raw == 0x24 else None
    vacation_year2 = bcd_byte(c[40]) if mode_raw == 0x24 else None

    out.update({
        "room_temperature_c": c[1] / 2.0,
        "room_temperature_status": "CONFIRMED",
        "room_temperature_correction_note": (
            "RS10 manual identifies KORREKTUR as room-temperature compensation (±2.5 K); "
            "controlled tests show it affects reported P02; no separate correction field has been identified."
        ),
        "active_room_setpoint_c": c[3] / 2.0,
        "active_room_setpoint_status": "CONFIRMED",
        "operating_mode": mode,
        "operating_mode_raw": mode_raw,
        "operating_mode_status": "CONFIRMED",
        "hot_water_setpoint_c": c[9] / 2.0,
        "hot_water_setpoint_status": "CONFIRMED",
        "p11_raw": c[10],
        "manual_dhw_recharge_state": {0: "off", 1: "request_from_rs10", 2: "accepted_or_active"}.get(c[10], f"unknown_0x{c[10]:02x}"),
        "manual_dhw_recharge_status": "LIKELY_DIRECTION_SENSITIVE",
        "day_setpoint_c": c[36] / 2.0,
        "day_setpoint_status": "CONFIRMED",
        "night_setpoint_c": c[37] / 2.0,
        "night_setpoint_status": "CONFIRMED",
        "timed_end_minute": minute,
        "timed_end_hour": hour,
        "timed_end_weekday_raw": weekday_raw,
        "timed_end_weekday": WEEKDAYS.get(weekday_raw) if weekday_raw is not None else None,
        "timed_end_status": "CONFIRMED" if mode_raw in (0x13, 0x14) else None,
        "vacation_end_day": vacation_day,
        "vacation_end_month": vacation_month,
        "vacation_end_year": 2000 + vacation_year2 if vacation_year2 is not None else None,
        "vacation_end_status": "CONFIRMED_ON_TESTED_INSTALLATION" if mode_raw == 0x24 else None,
    })
    return out


def decode_program_request(frame: Frame) -> dict:
    mapping = {
        "010e": ("boiler", 1),
        "010f": ("boiler", 2),
        "0110": ("boiler", 3),
        "0112": ("hot_water", None),
        "0114": ("rs10_parameters", None),
    }
    program, number = mapping[frame.message_type]
    out = {
        "kind": "program_request" if program != "rs10_parameters" else "parameter_block_request",
        "program": program,
        "status": "CONFIRMED_BY_UI_EXPERIMENT",
    }
    if number is not None:
        out["program_number"] = number
    return out


def _decode_schedule_time(min_raw: int, hour_raw: int) -> Optional[str]:
    minute = bcd_byte(min_raw)
    hour = bcd_byte(hour_raw)
    if minute is None or hour is None or not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def decode_boiler_week_program(frame: Frame) -> dict:
    """Decode confirmed Kessel PROG 1/2/3 blocks: 800E/800F/8010."""
    program_by_type = {"800e": 1, "800f": 2, "8010": 3}
    subtype_by_type = {"800e": 0x0E, "800f": 0x0F, "8010": 0x10}
    program_number = program_by_type[frame.message_type]
    subtype = subtype_by_type[frame.message_type]
    c = frame.content
    out = {
        "kind": "boiler_week_program",
        "program_number": program_number,
        "status": "CONFIRMED",
    }
    data = c[1:] if c and c[0] == subtype else c
    if len(data) < 105:
        out["error"] = (
            f"{frame.message_type.upper()} content too short "
            f"({len(data)} program bytes, expected >= 105)"
        )
        return out
    days = []
    for day_idx in range(7):
        block = data[day_idx*15:(day_idx+1)*15]
        windows = []
        for w in range(3):
            r = block[w*5:(w+1)*5]
            sm, sh, temp_raw, em, eh = r
            empty = (sm, sh, em, eh) == (0, 0, 0, 0)
            windows.append({
                "raw": r.hex(" "),
                "empty": empty,
                "start": None if empty else _decode_schedule_time(sm, sh),
                "end": None if empty else _decode_schedule_time(em, eh),
                "setpoint_c": temp_raw / 2.0,
                "setpoint_raw": temp_raw,
            })
        days.append({"weekday": WEEKDAYS[day_idx+1], "windows": windows})
    out["days"] = days
    out["trailing_hex"] = data[105:].hex(" ")
    out["temperature_note"] = (
        "Slot temperature bytes are confirmed value/2 °C and were observed shifting "
        "with the global TAG-SOLL setting, including retained values in empty slots."
    )
    return out


def decode_8012(frame: Frame) -> dict:
    c = frame.content
    out = {"kind": "dhw_week_program", "status": "CONFIRMED"}
    data = c[1:] if c and c[0] == 0x12 else c
    if len(data) < 105:
        out["error"] = f"8012 content too short ({len(data)} program bytes, expected >= 105)"
        return out
    days = []
    for day_idx in range(7):
        block = data[day_idx*15:(day_idx+1)*15]
        windows = []
        for w in range(3):
            r = block[w*5:(w+1)*5]
            sm, sh, set_raw, em, eh = r
            empty = (sm, sh, em, eh) == (0, 0, 0, 0)
            windows.append({
                "raw": r.hex(" "),
                "empty": empty,
                "start": None if empty else _decode_schedule_time(sm, sh),
                "end": None if empty else _decode_schedule_time(em, eh),
                "dhw_setpoint_raw": set_raw,
                "dhw_setpoint_c": set_raw / 2.0,
                "dhw_setpoint_status": "LIKELY_MANUAL_MATCH_NOT_YET_CONTROLLED",
                "marker_raw": set_raw,
                "marker_ok": set_raw == 0x64,
            })
        days.append({"weekday": WEEKDAYS[day_idx+1], "windows": windows})
    out["days"] = days
    out["trailing_hex"] = data[105:].hex(" ")
    return out


def decode_8014(frame: Frame) -> dict:
    """Partially decode the RS10 long-Haus parameter/configuration block.

    Parameter-byte numbering here starts *after* the 0x14 subtype byte. This avoids
    confusing these configuration offsets with the document-wide payload P-numbering.
    Thus parameter byte 30 is frame.content[30] (document-wide payload P31), and
    parameter byte 92 is frame.content[92] (document-wide payload P93).
    """
    c = frame.content
    out = {"kind": "rs10_parameter_block", "status": "PARTIALLY_DECODED"}
    data = c[1:] if c and c[0] == 0x14 else c
    if len(data) < 92:
        out["error"] = f"8014 content too short ({len(data)} parameter bytes, expected >= 92)"
        return out

    reduced_raw = data[7]   # parameter byte 8 after subtype, document P9
    boiler_raw = data[29]   # parameter byte 30 after subtype, document P31
    slope_raw = data[34]    # parameter byte 35 after subtype, document P36
    legionella_raw = data[80]  # parameter byte 81 after subtype, document P82
    dhw_raw = data[91]      # parameter byte 92 after subtype, document P93

    reduced_map = {0: "ECO", 1: "AbS"}
    boiler_map = {1: "program_1", 2: "program_2", 3: "program_3"}
    dhw_map = {1: "program_1", 2: "program_2", 3: "program_3"}

    if legionella_raw == 0:
        legionella = "AUS"
        legionella_status = "CONFIRMED"
    elif legionella_raw in (1, 2):
        legionella = str(legionella_raw)
        legionella_status = "CONFIRMED"
    elif 3 <= legionella_raw <= 7:
        legionella = str(legionella_raw)
        legionella_status = "LIKELY_VALUE_MAPPING_UI_OFFERS_1_TO_7"
    else:
        legionella = f"unknown_0x{legionella_raw:02x}"
        legionella_status = "UNKNOWN_VALUE"

    out.update({
        "parameter_byte_8_raw": reduced_raw,
        "reduced_mode": reduced_map.get(reduced_raw),
        "reduced_mode_status": "CONFIRMED" if reduced_raw in reduced_map else "UNKNOWN_VALUE",
        "parameter_byte_30_raw": boiler_raw,
        "boiler_program_selected": boiler_map.get(boiler_raw),
        "boiler_program_selected_status": (
            "CONFIRMED" if boiler_raw in boiler_map else "UNKNOWN_VALUE"
        ),
        "parameter_byte_35_raw": slope_raw,
        "heating_curve_slope": slope_raw / 20.0,
        "heating_curve_slope_status": "CONFIRMED",
        "parameter_byte_81_raw": legionella_raw,
        "legionella_setting": legionella,
        "legionella_setting_status": legionella_status,
        "parameter_byte_92_raw": dhw_raw,
        "hot_water_program_selected": dhw_map.get(dhw_raw),
        "hot_water_program_selected_status": (
            "LIKELY_FOR_VALUE_1"
            if dhw_raw == 1
            else "CONFIRMED_FOR_VALUES_2_3"
            if dhw_raw in (2, 3)
            else "UNKNOWN_VALUE"
        ),
        "numbering_note": (
            "8014 parameter-byte numbering starts after subtype 0x14; "
            "byte 8=P9, byte 30=P31, byte 35=P36, byte 81=P82, byte 92=P93."
        ),
    })
    return out


def decode_frame(frame: Frame) -> dict:
    base = {
        "type": frame.message_type,
        "source": f"{frame.source:02x}",
        "source_name": ADDRESS_NAMES.get(frame.source),
        "destination": f"{frame.destination:02x}",
        "destination_name": ADDRESS_NAMES.get(frame.destination),
        "length_byte": frame.length_byte,
        "crc_ok": frame.crc_ok,
        "crc_stored": f"{frame.crc_stored:04x}",
        "crc_calculated": f"{frame.crc_calculated:04x}",
        "content_hex": frame.content.hex(" "),
        "raw_hex": frame.raw.hex(" "),
    }
    if frame.message_type == "0905":
        base["decoded"] = decode_0905(frame)
    elif frame.message_type == "2004":
        base["decoded"] = decode_2004(frame)
    elif frame.message_type == "2806":
        base["decoded"] = decode_2806(frame)
    elif frame.message_type == "4002":
        base["decoded"] = decode_4002(frame)
    elif frame.message_type in ("800e", "800f", "8010"):
        base["decoded"] = decode_boiler_week_program(frame)
    elif frame.message_type == "8012":
        base["decoded"] = decode_8012(frame)
    elif frame.message_type == "8014":
        base["decoded"] = decode_8014(frame)
    elif frame.message_type in ("010e", "010f", "0110", "0112", "0114"):
        base["decoded"] = decode_program_request(frame)
    else:
        base["decoded"] = {"kind": "unknown"}
    return base


# ---------------------------------------------------------------------------
# Formatting / analysis
# ---------------------------------------------------------------------------

def endpoint(addr: int) -> str:
    name = ADDRESS_NAMES.get(addr)
    return f"{addr:02X}({name})" if name else f"{addr:02X}"


def format_human(frame: Frame, decoded: dict) -> str:
    d = decoded["decoded"]
    prefix = f"TYPE={frame.message_type} {endpoint(frame.source)}->{endpoint(frame.destination)} CRC={'OK' if frame.crc_ok else 'BAD'}"

    if frame.message_type == "0905":
        return f"{d.get('timestamp', 'invalid-time')}  {prefix}"

    if frame.message_type == "2004" and "error" not in d:
        return (
            f"{prefix}  outside={d['outside_temperature_c']:.1f}°C  "
            f"gamma-kessel/vorlauf={d['gamma_boiler_flow_temperature_c']:.1f}°C[LIKELY]  "
            f"P17=0x{d['p17_raw']:02X}[UNKNOWN]  "
            f"P18=0x{d['p18_raw']:02X}[UNKNOWN]  "
            f"P33=0x{d['p33_raw']:02X}[UNKNOWN]"
        )

    if frame.message_type == "4002" and "error" not in d:
        return (
            f"{prefix}  DHW-actual={d['hot_water_actual_c']:.1f}°C "
            f"(P08=0x{d['p08_raw']:02X})[CONFIRMED]"
        )

    if frame.message_type == "2806" and "error" not in d:
        timed = ""
        if d["operating_mode"] in ("party", "away"):
            hh, mm = d.get("timed_end_hour"), d.get("timed_end_minute")
            wd = d.get("timed_end_weekday") or f"weekday#{d.get('timed_end_weekday_raw')}"
            if hh is not None and mm is not None:
                timed = f"  until={wd} {hh:02d}:{mm:02d}"
            elif d["operating_mode"] == "vacation":
                day = d.get("vacation_end_day")
                month = d.get("vacation_end_month")
                year = d.get("vacation_end_year")
                if None not in (day, month, year):
                    timed = f"  vacation-until={day:02d}.{month:02d}.{year:04d}"
        return (
            f"{prefix}  room={d['room_temperature_c']:.1f}°C  "
            f"active-set={d['active_room_setpoint_c']:.1f}°C  "
            f"mode={d['operating_mode']}(0x{d['operating_mode_raw']:02X})  "
            f"DHW-set={d['hot_water_setpoint_c']:.1f}°C  "
            f"DHW-recharge={d['manual_dhw_recharge_state']}(P11=0x{d['p11_raw']:02X})  "
            f"day={d['day_setpoint_c']:.1f}°C  night={d['night_setpoint_c']:.1f}°C"
            f"{timed}"
        )

    if frame.message_type in ("010e", "010f", "0110", "0112", "0114"):
        labels = {
            "010e": "BOILER PROGRAM 1 REQUEST",
            "010f": "BOILER PROGRAM 2 REQUEST",
            "0110": "BOILER PROGRAM 3 REQUEST",
            "0112": "HOT-WATER PROGRAM REQUEST",
            "0114": "RS10 PARAMETER BLOCK REQUEST",
        }
        return f"{prefix}  {labels[frame.message_type]}"

    if frame.message_type in ("800e", "800f", "8010", "8012") and "error" not in d:
        if frame.message_type == "8012":
            label = "HOT-WATER WEEK PROGRAM"
        else:
            label = f"BOILER WEEK PROGRAM {d['program_number']}"
        lines = [f"{prefix}  {label}"]
        for day in d["days"]:
            parts = []
            for w in day["windows"]:
                if w["empty"]:
                    parts.append("--")
                elif frame.message_type in ("800e", "800f", "8010"):
                    parts.append(f"{w['start']}-{w['end']} @ {w['setpoint_c']:.1f}°C")
                else:
                    parts.append(
                        f"{w['start']}-{w['end']} @ {w['dhw_setpoint_c']:.1f}°C"
                        f" [set=0x{w['dhw_setpoint_raw']:02X}, LIKELY]"
                    )
            lines.append(f"  {day['weekday']:<9} " + " | ".join(parts))
        return "\n".join(lines)

    if frame.message_type == "8014" and "error" not in d:
        boiler = d.get("boiler_program_selected") or f"unknown_0x{d['parameter_byte_30_raw']:02X}"
        dhw = d.get("hot_water_program_selected") or f"unknown_0x{d['parameter_byte_92_raw']:02X}"
        return (
            f"{prefix}  RS10 PARAMETER BLOCK  "
            f"Reduziert={d.get('reduced_mode') or 'unknown'} (param#8=0x{d['parameter_byte_8_raw']:02X})  "
            f"Kessel-PROG={boiler} (param#30=0x{d['parameter_byte_30_raw']:02X})  "
            f"Steilheit={d['heating_curve_slope']:.2f} (param#35=0x{d['parameter_byte_35_raw']:02X})  "
            f"Legionellen-WW={d['legionella_setting']} (param#81=0x{d['parameter_byte_81_raw']:02X})  "
            f"WW-PROG={dhw} (param#92=0x{d['parameter_byte_92_raw']:02X})"
        )

    return f"{prefix}  RAW={frame.content.hex(' ')}"


def semantic_signature(frame: Frame) -> tuple:
    """Known-state signature used by --changes; unknown messages fall back to full raw frame."""
    d = decode_frame(frame)["decoded"]
    if frame.message_type == "0905":
        # Don't let every second defeat --changes: minute-level clock signature.
        return (frame.message_type, frame.source, frame.destination, d.get("year"), d.get("month"), d.get("day"), d.get("hour"), d.get("minute"))
    if frame.message_type == "2004" and "error" not in d:
        return (frame.message_type, frame.source, frame.destination, d["outside_temperature_c"], d["p17_raw"], d["p18_raw"], d["gamma_boiler_flow_temperature_c"], d["p33_raw"])
    if frame.message_type in ("800e", "800f", "8010", "8012", "8014") and "error" not in d:
        return (frame.message_type, frame.source, frame.destination, frame.content)
    if frame.message_type == "4002" and "error" not in d:
        return (frame.message_type, frame.source, frame.destination, d["p08_raw"])
    if frame.message_type == "2806" and "error" not in d:
        return (
            frame.message_type, frame.source, frame.destination,
            d["room_temperature_c"], d["active_room_setpoint_c"], d["operating_mode_raw"],
            d["hot_water_setpoint_c"], d["p11_raw"], d["day_setpoint_c"], d["night_setpoint_c"],
            d["timed_end_minute"], d["timed_end_hour"], d["timed_end_weekday_raw"],
            d["vacation_end_day"], d["vacation_end_month"], d["vacation_end_year"],
        )
    if frame.message_type in ("010e", "010f", "0110", "0112", "0114"):
        return (frame.message_type, frame.source, frame.destination, frame.content)
    return (frame.message_type, frame.source, frame.destination, frame.raw)


def iter_deduplicated(frames: Iterable[Frame]) -> Iterator[Frame]:
    last_raw = None
    for frame in frames:
        if frame.raw != last_raw:
            yield frame
        last_raw = frame.raw


def iter_changes(frames: Iterable[Frame]) -> Iterator[Frame]:
    """Suppress unchanged semantic state per (type, source, destination)."""
    last: dict[tuple[str, int, int], tuple] = {}
    for frame in frames:
        key = (frame.message_type, frame.source, frame.destination)
        sig = semantic_signature(frame)
        if last.get(key) != sig:
            yield frame
            last[key] = sig


def field_stats(frames: Iterable[Frame], wanted_type: str) -> dict:
    selected = [f for f in frames if f.message_type == wanted_type]
    if not selected:
        return {"type": wanted_type, "count": 0, "positions": []}
    max_len = max(len(f.content) for f in selected)
    positions = []
    for idx in range(max_len):
        vals = [f.content[idx] for f in selected if idx < len(f.content)]
        counter = Counter(vals)
        positions.append({
            "position": idx + 1,
            "count": len(vals),
            "min": min(vals),
            "max": max(vals),
            "distinct": len(counter),
            "most_common": [{"value": f"{v:02x}", "count": n} for v, n in counter.most_common(8)],
        })
    return {"type": wanted_type, "count": len(selected), "positions": positions}


def topology(frames: Iterable[Frame]) -> dict:
    links: Counter[tuple[int, int]] = Counter()
    by_type: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
    for f in frames:
        key = (f.source, f.destination)
        links[key] += 1
        by_type[key][f.message_type] += 1
    out = []
    for (src, dst), count in links.most_common():
        out.append({
            "source": f"{src:02x}", "source_name": ADDRESS_NAMES.get(src),
            "destination": f"{dst:02x}", "destination_name": ADDRESS_NAMES.get(dst),
            "count": count,
            "types": dict(by_type[(src, dst)].most_common()),
        })
    return {"links": out}


# ---------------------------------------------------------------------------
# File mode
# ---------------------------------------------------------------------------

def run_file(args: argparse.Namespace) -> int:
    path = Path(args.input)
    raw = read_input(path, args.input_format)
    stream, normalization, norm_info = normalize_stream(raw, args.normalize)
    frames = list(iter_frames(stream, accept_bad_crc=args.accept_bad_crc))
    valid_count = sum(f.crc_ok for f in frames)

    selected: Iterable[Frame] = frames if args.no_dedupe else iter_deduplicated(frames)
    if args.changes:
        selected = iter_changes(selected)
    output_frames = list(selected)

    if args.type:
        wanted = args.type.lower()
        output_frames = [f for f in output_frames if f.message_type == wanted]

    summary = {
        "input": str(path),
        "input_bytes": len(raw),
        "normalization": normalization,
        "normalization_info": norm_info,
        "frames_total": len(frames),
        "frames_crc_ok": valid_count,
        "frames_crc_bad": len(frames) - valid_count,
        "frames_after_dedup_changes_filter": len(output_frames),
        "types": dict(Counter(f.message_type for f in frames).most_common()),
    }

    if args.topology:
        print(json.dumps({"summary": summary, "topology": topology(frames)}, indent=2))
        if not args.show and not args.stats:
            return 0

    if args.stats:
        stats_type = (args.type or args.stats_type or "2004").lower()
        print(json.dumps({"summary": summary, "field_stats": field_stats(frames, stats_type)}, indent=2))
        if not args.show:
            return 0

    if args.summary:
        print(json.dumps(summary, indent=2))
        if not args.show and not args.jsonl:
            return 0

    json_handle: Optional[TextIO] = None
    if args.jsonl:
        json_handle = Path(args.jsonl).open("w", encoding="utf-8")

    try:
        shown = 0
        for frame in output_frames:
            decoded = decode_frame(frame)
            if json_handle:
                json_handle.write(json.dumps(decoded, ensure_ascii=False) + "\n")
            if args.show:
                print(format_human(frame, decoded))
                if args.raw:
                    print("  RAW:", frame.raw.hex(" "))
            shown += 1
            if args.limit and shown >= args.limit:
                break
    finally:
        if json_handle:
            json_handle.close()
    return 0


# ---------------------------------------------------------------------------
# Live serial mode
# ---------------------------------------------------------------------------

def serial_bytes(port: str, baud: int) -> Iterator[bytes]:
    try:
        import serial  # type: ignore
    except ImportError:
        raise SystemExit("--serial requires pyserial: python -m pip install pyserial")

    with serial.Serial(port, baudrate=baud, bytesize=8, parity="N", stopbits=1, timeout=1) as ser:
        while True:
            chunk = ser.read(4096)
            if chunk:
                yield chunk


class LiveExtractor:
    def __init__(self, accept_bad_crc: bool = False):
        self.buffer = bytearray()
        self.accept_bad_crc = accept_bad_crc

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        found: list[Frame] = []
        while True:
            try:
                start = self.buffer.index(START_BYTE)
            except ValueError:
                # Keep a tiny tail only; no start marker means no useful frame prefix.
                self.buffer.clear()
                break

            if start:
                del self.buffer[:start]
            if len(self.buffer) < 4:
                break

            total = self.buffer[3] + 8
            if len(self.buffer) < total:
                break

            candidate = bytes(self.buffer[:total])
            frame = make_frame(candidate)
            if frame and (frame.crc_ok or self.accept_bad_crc):
                found.append(frame)
                del self.buffer[:total]
            else:
                del self.buffer[0]
        return found


class InterleavedFFLiveExtractor:
    """Stateful extractor for captures encoded as BYTE,FF,BYTE,FF,... ."""
    def __init__(self, accept_bad_crc: bool = False):
        self.buffer = bytearray()
        self.accept_bad_crc = accept_bad_crc

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        found: list[Frame] = []
        while True:
            try:
                start = self.buffer.index(START_BYTE)
            except ValueError:
                self.buffer.clear()
                break
            if start:
                del self.buffer[:start]
            # Need encoded logical header: 82 FF src FF dst FF LL FF
            if len(self.buffer) < 8:
                break
            if not all(self.buffer[i] == 0xFF for i in (1, 3, 5, 7)):
                del self.buffer[0]
                continue
            ll = self.buffer[6]
            logical_total = ll + 8
            physical_total = logical_total * 2
            if len(self.buffer) < physical_total:
                break
            if not all(self.buffer[i] == 0xFF for i in range(1, physical_total, 2)):
                del self.buffer[0]
                continue
            candidate = bytes(self.buffer[i] for i in range(0, physical_total, 2))
            frame = make_frame(candidate)
            if frame and (frame.crc_ok or self.accept_bad_crc):
                found.append(frame)
                del self.buffer[:physical_total]
            else:
                del self.buffer[0]
        return found


def run_serial(args: argparse.Namespace) -> int:
    normalization = args.normalize
    decided: Optional[str] = None if normalization == "auto" else normalization
    probe = bytearray()
    extractor = LiveExtractor(args.accept_bad_crc)
    interleaved_extractor = InterleavedFFLiveExtractor(args.accept_bad_crc)
    last_raw = None
    last_semantic: dict[tuple[str, int, int], tuple] = {}

    if decided:
        print(f"# live normalization: {decided}", file=sys.stderr)

    def emit(frame: Frame) -> None:
        nonlocal last_raw
        if not args.no_dedupe and frame.raw == last_raw:
            return
        last_raw = frame.raw
        if args.type and frame.message_type != args.type.lower():
            return
        if args.changes:
            key = (frame.message_type, frame.source, frame.destination)
            sig = semantic_signature(frame)
            if last_semantic.get(key) == sig:
                return
            last_semantic[key] = sig
        decoded = decode_frame(frame)
        print(format_human(frame, decoded), flush=True)
        if args.raw:
            print("  RAW:", frame.raw.hex(" "), flush=True)

    for chunk in serial_bytes(args.serial, args.baud):
        if decided is None:
            probe.extend(chunk)
            probe_bytes = bytes(probe)
            raw_score = count_valid_frames(probe_bytes, limit=10)
            stripped_probe = probe_bytes.replace(b"\xff", b"")
            stripped_score = count_valid_frames(stripped_probe, limit=10)
            deint_probe = deinterleave_ff_separators(probe_bytes)
            deint_score = count_valid_frames(deint_probe, limit=10)

            # Decide as soon as one representation demonstrates valid framing.
            if raw_score or stripped_score or deint_score or len(probe) >= 16384:
                best = max(raw_score, stripped_score, deint_score)
                if deint_score == best and best > 0:
                    decided, data = "deinterleave-ff", deint_probe
                elif raw_score == best:
                    decided, data = "none", probe_bytes
                else:
                    decided, data = "strip-ff", stripped_probe
                print(
                    f"# live normalization auto-selected: {decided} "
                    f"(raw_valid={raw_score}, stripped_valid={stripped_score}, deinterleaved_valid={deint_score})",
                    file=sys.stderr,
                )
                probe.clear()
                if decided == "deinterleave-ff":
                    for frame in interleaved_extractor.feed(probe_bytes):
                        emit(frame)
                else:
                    for frame in extractor.feed(data):
                        emit(frame)
            continue

        if decided == "deinterleave-ff":
            frames_now = interleaved_extractor.feed(chunk)
        else:
            data = chunk.replace(b"\xff", b"") if decided == "strip-ff" else chunk
            frames_now = extractor.feed(data)
        for frame in frames_now:
            emit(frame)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read-only Gamma / Gamma RS10 RS485 parser")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("input", nargs="?", help="capture file (binary or ASCII hex dump)")
    src.add_argument("--serial", help="live serial device, e.g. /dev/ttyUSB1")

    p.add_argument("--input-format", choices=("auto", "hex", "binary", "log"), default="auto")
    p.add_argument(
        "--normalize", choices=("auto", "none", "strip-ff", "deinterleave-ff"), default="auto",
        help="capture normalization; auto compares CRC-valid frame counts",
    )
    p.add_argument("--baud", type=int, default=9600, help="serial baud rate (default: 9600)")
    p.add_argument("--type", help="only one message type, e.g. 2806")
    p.add_argument("--limit", type=int, default=50, help="maximum displayed frames; 0 = unlimited")
    p.add_argument("--show", action="store_true", help="display human-readable frames")
    p.add_argument("--raw", action="store_true", help="also display raw normalized frame bytes")
    p.add_argument("--jsonl", help="write decoded frames as JSON Lines")
    p.add_argument("--summary", action="store_true", help="show capture summary")
    p.add_argument("--stats", action="store_true", help="show per-byte statistics")
    p.add_argument("--stats-type", help="message type used by --stats")
    p.add_argument("--topology", action="store_true", help="show source/destination/type topology")
    p.add_argument("--changes", action="store_true", help="show semantic changes only, per type/src/dst")
    p.add_argument("--no-dedupe", action="store_true", help="do not suppress consecutive identical frames")
    p.add_argument("--accept-bad-crc", action="store_true", help="include frames with invalid CRC")
    return p


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    if not any((args.show, args.summary, args.stats, args.topology, args.jsonl)):
        args.summary = not bool(args.serial)
        args.show = True
    return run_serial(args) if args.serial else run_file(args)


if __name__ == "__main__":
    raise SystemExit(main())
