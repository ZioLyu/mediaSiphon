"""ASCII-only self check for core logic (no third-party deps needed)."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from siphon.progress import parse_line, parse_chunk
from siphon.spec import FetchSpec, build_argv, sanitize_title
from siphon.settings import SiphonSettings
from siphon.store import JobStore, STATUS_DONE


def main() -> int:
    vod = "12/345 45.6% 1.2MB/30.5MB 3.4MBps 00:01:23"
    event = parse_line("\x1b[32m" + vod + "\x1b[0m")
    assert event is not None, "vod not parsed"
    assert event.done == 12 and event.total == 345, event
    assert event.percent == 45, event
    assert event.have_bytes > 1_000_000, event
    assert event.speed.startswith("3.4"), event

    live = "01m23s/10m00s 45/200 Recording 45% 2.1MBps"
    event = parse_line(live)
    assert event is not None and event.phase == "recording", event
    assert event.percent == 45, event

    waiting = "01m23s/10m00s 45/200 Waiting 45% -"
    assert parse_line(waiting).phase == "waiting"

    assert parse_line("WARN: nothing here") is None
    assert parse_line("random text") is None

    events, tail = parse_chunk("x\n" + vod + "\r\n" + live + "\npartial")
    assert len(events) == 2, events
    assert tail == "partial", repr(tail)

    settings = SiphonSettings(output_dir="C:/out")
    spec = FetchSpec(url="https://e/i.m3u8", title=sanitize_title("a/b:c*d?e"),
                     out_dir="C:/out", variant_width=1920, variant_height=1080,
                     variant_fps=30.0)
    argv = build_argv("engine.exe", spec, settings)

    joined = " ".join(argv)
    assert argv[0] == "https://e/i.m3u8", argv[0]
    assert "--select-video=res=1920*:frame=30*" in joined, joined
    assert "--decryption-engine=FFmpeg" in joined, joined
    assert "--thread-count=16" in joined, joined
    assert len(argv) == len(set(argv)), "duplicated tokens"

    # 变体选择器缺省行为
    plain = FetchSpec(url="https://e/i.m3u8", title="x", out_dir="C:/out")
    plain_argv = build_argv("engine.exe", plain, settings)
    assert "--select-video=best" in " ".join(plain_argv)

    assert sanitize_title('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i", sanitize_title('a/b:c*d?e"f<g>h|i')

    tmp = Path(tempfile.mkdtemp())
    store = JobStore(tmp / "t.db")
    record = store.insert(source_url="https://e/i.m3u8", title="demo", variant="1920x1080",
                          kind="vod", out_dir=str(tmp), file_hint="", argv=["a", "b"],
                          log_path="")
    assert store.get(record.job_id) is not None
    assert store.get(record.job_id).argv == ["a", "b"]
    store.update(record.job_id, status=STATUS_DONE, bytes_total=123)
    assert store.get(record.job_id).status == STATUS_DONE
    assert store.list(status=STATUS_DONE)[0].bytes_total == 123
    assert store.mark_orphans_failed() == 0
    store.delete(record.job_id)
    assert store.get(record.job_id) is None

    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
