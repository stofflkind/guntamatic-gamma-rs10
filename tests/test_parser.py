from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PARSER = Path(__file__).resolve().parents[1] / "parser" / "gamma_parser.py"
spec = importlib.util.spec_from_file_location("gamma_parser", PARSER)
gamma = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gamma
assert spec.loader is not None
spec.loader.exec_module(gamma)


def build_frame(source: int, destination: int, ll: int, content: bytes) -> bytes:
    """Build a valid Gamma frame for tests."""
    assert len(content) == ll + 1
    body = bytes([source, destination, ll]) + content
    crc = gamma.crc16_kermit(body)
    return bytes([gamma.START_BYTE]) + body + crc.to_bytes(2, "little") + bytes([gamma.END_BYTE])


def frame_2806(overrides: dict[int, int] | None = None):
    content = bytearray(41)
    content[0] = 0x06

    defaults = {
        2: 0x2C,   # room = 22.0 C
        4: 0x2A,   # active setpoint = 21.0 C
        7: 0x13,   # party
        10: 0x64,  # DHW setpoint = 50.0 C
        37: 0x2A,  # day = 21.0 C
        38: 0x20,  # night = 16.0 C
        39: 0x35,  # minute 35 BCD
        40: 0x00,  # hour 00 BCD
        41: 0x06,  # Saturday
    }
    if overrides:
        defaults.update(overrides)
    for position, value in defaults.items():
        content[position - 1] = value

    raw = build_frame(0x23, 0x20, 0x28, bytes(content))
    return gamma.make_frame(raw)


def frame_2004(p2=0x8A, p17=0x4E, p32=0x65, p33=0x4C):
    content = bytearray(33)
    content[0] = 0x04
    content[1] = p2
    content[16] = p17
    content[31] = p32
    content[32] = p33
    raw = build_frame(0x10, 0x20, 0x20, bytes(content))
    return gamma.make_frame(raw)


def test_crc16_kermit_standard_check_value():
    assert gamma.crc16_kermit(b"123456789") == 0x2189


def test_make_frame_extracts_valid_2806():
    frame = frame_2806()
    assert frame is not None
    assert frame.crc_ok
    assert frame.source == 0x23
    assert frame.destination == 0x20
    assert frame.message_type == "2806"
    assert len(frame.content) == 41


def test_2806_confirmed_fields():
    frame = frame_2806()
    decoded = gamma.decode_2806(frame)

    assert decoded["room_temperature_c"] == 22.0
    assert decoded["active_room_setpoint_c"] == 21.0
    assert decoded["operating_mode"] == "party"
    assert decoded["hot_water_setpoint_c"] == 50.0
    assert decoded["day_setpoint_c"] == 21.0
    assert decoded["night_setpoint_c"] == 16.0
    assert decoded["timed_end_minute"] == 35
    assert decoded["timed_end_hour"] == 0
    assert decoded["timed_end_weekday"] == "Saturday"


def test_all_confirmed_operating_modes():
    expected = {
        0x00: "automatic",
        0x03: "heating",
        0x04: "reduced",
        0x13: "party",
        0x14: "away",
    }
    for raw, name in expected.items():
        frame = frame_2806({7: raw})
        assert gamma.decode_2806(frame)["operating_mode"] == name


def test_2806_timed_end_friday_2329():
    frame = frame_2806({39: 0x29, 40: 0x23, 41: 0x05})
    decoded = gamma.decode_2806(frame)
    assert decoded["timed_end_minute"] == 29
    assert decoded["timed_end_hour"] == 23
    assert decoded["timed_end_weekday"] == "Friday"

def test_2806_vacation_end_date():
    frame = frame_2806({
        7: 0x24,   # vacation
        39: 0x15,  # day 15
        40: 0x10,  # month 10
        41: 0x26,  # year 2026
    })
    decoded = gamma.decode_2806(frame)

    assert decoded["operating_mode"] == "vacation"
    assert decoded["vacation_end_day"] == 15
    assert decoded["vacation_end_month"] == 10
    assert decoded["vacation_end_year"] == 2026

def test_2004_outside_and_boiler_temperature():
    frame = frame_2004()
    assert frame is not None and frame.crc_ok
    decoded = gamma.decode_2004(frame)

    assert decoded["outside_temperature_c"] == 17.0
    assert decoded["outside_temperature_status"] == "CONFIRMED"

    assert decoded["gamma_boiler_flow_temperature_c"] == 50.5
    assert decoded["gamma_boiler_flow_temperature_status"] == "LIKELY"
    assert decoded["p17_raw"] == 0x4E
    assert decoded["p17_status"] == "UNKNOWN"
    assert decoded["p33_raw"] == 0x4C


def test_bcd_byte_valid_and_invalid():
    assert gamma.bcd_byte(0x00) == 0
    assert gamma.bcd_byte(0x29) == 29
    assert gamma.bcd_byte(0x59) == 59
    assert gamma.bcd_byte(0xFA) is None

def test_deinterleave_ff_normalization_prefers_lossless_stream():
    frame = frame_2806().raw
    noisy = b"".join(bytes([b, 0xFF]) for b in frame)
    normalized, mode, info = gamma.normalize_stream(noisy, "auto")

    assert mode == "deinterleave-ff"
    assert normalized == frame
    assert info["normalized_bytes"] == len(frame)
    assert info["probe_deinterleaved_valid_frames"] == 1
    assert gamma.count_valid_frames(normalized) == 1


def test_iter_frames_finds_multiple_frames_and_ignores_noise():
    a = frame_2004().raw
    b = frame_2806().raw
    stream = b"\x00\x01garbage" + a + b"\x55\x66" + b
    frames = list(gamma.iter_frames(stream))
    assert [f.message_type for f in frames] == ["2004", "2806"]


def test_iter_deduplicated_removes_only_consecutive_exact_duplicates():
    a = frame_2806({2: 0x2C})
    b = frame_2806({2: 0x2D})
    result = list(gamma.iter_deduplicated([a, a, b, b, a]))
    assert len(result) == 3
    assert gamma.decode_2806(result[0])["room_temperature_c"] == 22.0
    assert gamma.decode_2806(result[1])["room_temperature_c"] == 22.5
    assert gamma.decode_2806(result[2])["room_temperature_c"] == 22.0


def test_iter_changes_reports_semantic_change():
    a1 = frame_2806({2: 0x2C})
    a2 = frame_2806({2: 0x2C})
    b = frame_2806({2: 0x2D})
    result = list(gamma.iter_changes([a1, a2, b]))
    assert len(result) == 2
    assert gamma.decode_2806(result[0])["room_temperature_c"] == 22.0
    assert gamma.decode_2806(result[1])["room_temperature_c"] == 22.5


def test_live_extractor_handles_split_frame():
    raw = frame_2004().raw
    extractor = gamma.LiveExtractor()

    assert extractor.feed(raw[:7]) == []
    frames = extractor.feed(raw[7:])

    assert len(frames) == 1
    assert frames[0].message_type == "2004"
    assert frames[0].crc_ok


def test_bad_crc_is_rejected_by_default():
    raw = bytearray(frame_2004().raw)
    raw[10] ^= 0x01
    assert list(gamma.iter_frames(bytes(raw))) == []

    frames = list(gamma.iter_frames(bytes(raw), accept_bad_crc=True))
    assert len(frames) == 1
    assert not frames[0].crc_ok
