"""进度解析的回归测试。"""

from siphon.progress import parse_chunk, parse_line, strip_ansi

VOD_LINE = "12/345 45.6% 1.2MB/30.5MB 3.4MBps 00:01:23"
LIVE_LINE = "01m23s/10m00s 45/200 Recording 45% 2.1MBps"


def test_strip_ansi_removes_color_codes():
    assert strip_ansi("\x1b[32mabc\x1b[0m") == "abc"


def test_parse_vod_progress():
    event = parse_line(VOD_LINE)
    assert event is not None
    assert event.phase == "fetching"
    assert event.done == 12
    assert event.total == 345
    assert event.percent == 45
    assert event.total_bytes == int(30.5 * 1024 ** 2)
    assert event.speed.startswith("3.4")
    assert event.eta == "00:01:23"


def test_parse_vod_with_ansi_prefix():
    event = parse_line("\x1b[36m" + VOD_LINE + "\x1b[0m")
    assert event is not None and event.percent == 45


def test_parse_live_recording():
    event = parse_line(LIVE_LINE)
    assert event is not None
    assert event.phase == "recording"
    assert event.percent == 45
    assert event.eta == "10m00s"


def test_parse_live_waiting_without_speed():
    event = parse_line("01m23s/10m00s 45/200 Waiting 45% -")
    assert event is not None
    assert event.phase == "waiting"
    assert event.speed == "0 B/s"


def test_ignore_warning_and_noise():
    assert parse_line("WARN: something went wrong") is None
    assert parse_line("Downloading started") is None
    assert parse_line("   ") is None


def test_parse_chunk_keeps_partial_tail():
    events, tail = parse_chunk("noise\n" + VOD_LINE + "\r\n" + LIVE_LINE + "\npartial")
    assert len(events) == 2
    assert tail == "partial"


def test_parse_chunk_handles_trailing_newline():
    events, tail = parse_chunk(VOD_LINE + "\n")
    assert len(events) == 1
    assert tail == ""


def test_speed_normalization_units():
    assert parse_line("1/2 50% 512KB/1MB 900KBps 00:00:10").speed == "900.0 KB/s"
    assert parse_line("1/2 50% 1GB/2GB 1.5GBps 00:00:10").speed == "1.5 GB/s"
