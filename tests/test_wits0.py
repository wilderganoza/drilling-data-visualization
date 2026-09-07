"""Unit tests for the WITS0 frame parser and the item->column mapper.
Pure logic, no sockets/DB — see app/services/realtime/wits0.py."""
import pytest

from app.services.realtime.wits0 import (
    Wits0Frame, encode_wits0_frame, parse_wits0_text,
)
from app.services.realtime.wits0_map import WitsColumn, map_frame_to_row


def test_parses_a_single_well_formed_frame():
    text = "&&\r\n0108 4521.30\r\n0110 18.40\r\n0113 112\r\n!!\r\n"
    frames = parse_wits0_text(text)
    assert len(frames) == 1
    assert frames[0].raw(1, 8) == "4521.30"
    assert frames[0].as_float(1, 8) == pytest.approx(4521.30)
    assert frames[0].as_float(1, 13) == pytest.approx(112.0)


def test_parses_multiple_consecutive_frames():
    text = "&&\n0108 100\n!!\n&&\n0108 200\n!!\n"
    frames = parse_wits0_text(text)
    assert len(frames) == 2
    assert frames[0].as_float(1, 8) == 100
    assert frames[1].as_float(1, 8) == 200


def test_ignores_data_lines_outside_a_frame():
    # A stray line before the first "&&" (noise on the wire) must not become a phantom frame.
    text = "0199 garbage\n&&\n0108 50\n!!\n"
    frames = parse_wits0_text(text)
    assert len(frames) == 1
    assert frames[0].as_float(1, 8) == 50


def test_incomplete_frame_without_closing_marker_is_dropped():
    # No "!!" ever arrives — the frame must not leak into the next one.
    text = "&&\n0108 50\n&&\n0110 10\n!!\n"
    frames = parse_wits0_text(text)
    assert len(frames) == 1
    # Only the second (properly closed) frame survives; the first was discarded when the second "&&" arrived.
    assert frames[0].raw(1, 8) is None
    assert frames[0].as_float(1, 10) == 10


def test_non_numeric_slot_code_is_skipped_not_fatal():
    text = "&&\nABCD 1\n0108 5\n!!\n"
    frames = parse_wits0_text(text)
    assert len(frames) == 1
    assert frames[0].as_float(1, 8) == 5


def test_missing_or_non_numeric_value_returns_none():
    frame = Wits0Frame(slots={(1, 8): "not-a-number", (1, 10): ""})
    assert frame.as_float(1, 8) is None
    assert frame.as_float(1, 10) is None
    assert frame.as_float(9, 9) is None  # slot never present at all


def test_encode_then_parse_round_trips():
    encoded = encode_wits0_frame({(1, 8): "1234.5", (1, 13): "80"})
    frames = parse_wits0_text(encoded)
    assert len(frames) == 1
    assert frames[0].as_float(1, 8) == pytest.approx(1234.5)
    assert frames[0].as_float(1, 13) == pytest.approx(80.0)


def test_map_frame_to_row_only_includes_mapped_and_present_slots():
    frame = Wits0Frame(slots={(1, 8): "1000.0", (1, 99): "999"})  # (1, 99) is deliberately unmapped
    item_map = {(1, 8): WitsColumn("bit_depth_feet")}
    row = map_frame_to_row(frame, item_map=item_map)
    assert row == {"bit_depth_feet": 1000.0}


def test_map_frame_to_row_applies_scale_and_offset():
    # e.g. a channel sent in a different unit than our column stores
    frame = Wits0Frame(slots={(2, 1): "10"})
    item_map = {(2, 1): WitsColumn("standpipe_pressure_psi", scale=2.0, offset=1.0)}
    row = map_frame_to_row(frame, item_map=item_map)
    assert row == {"standpipe_pressure_psi": 21.0}  # 10*2 + 1


def test_map_frame_to_row_empty_map_yields_empty_row():
    frame = Wits0Frame(slots={(1, 8): "1000.0"})
    assert map_frame_to_row(frame, item_map={}) == {}


@pytest.mark.asyncio
async def test_iter_wits0_frames_reads_frames_as_they_close():
    from app.services.realtime.wits0 import iter_wits0_frames

    class FakeReader:
        """Minimal stand-in for asyncio.StreamReader.readline()."""
        def __init__(self, lines):
            self._lines = list(lines)

        async def readline(self):
            if not self._lines:
                return b""
            return self._lines.pop(0)

    reader = FakeReader([
        b"&&\r\n", b"0108 111\r\n", b"!!\r\n",
        b"&&\r\n", b"0108 222\r\n", b"!!\r\n",
    ])
    frames = [f async for f in iter_wits0_frames(reader)]
    assert len(frames) == 2
    assert frames[0].as_float(1, 8) == 111
    assert frames[1].as_float(1, 8) == 222
