"""命令行构造与任务台账的回归测试。"""

from pathlib import Path

import pytest

from siphon.settings import SiphonSettings
from siphon.spec import FetchSpec, build_argv, expected_suffixes, sanitize_title
from siphon.store import JobStore, STATUS_DONE, STATUS_FAILED, STATUS_RUNNING


@pytest.fixture()
def settings(tmp_path: Path) -> SiphonSettings:
    cfg = SiphonSettings(output_dir=str(tmp_path))
    cfg.normalize()
    return cfg


def test_sanitize_title_strips_illegal_chars():
    assert sanitize_title('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i"


def test_sanitize_title_falls_back_when_empty():
    assert sanitize_title("   ") == "untitled"
    assert sanitize_title("//:") == "untitled"


def test_build_argv_core_arguments(settings: SiphonSettings, tmp_path: Path):
    spec = FetchSpec(url="https://e/i.m3u8", title="demo", out_dir=str(tmp_path),
                     variant_width=1920, variant_height=1080, variant_fps=30.0)
    argv = build_argv("engine", spec, settings)
    joined = " ".join(argv)

    assert argv[0] == "https://e/i.m3u8"
    assert f"--save-dir={tmp_path}" in joined
    assert "--save-name=demo" in joined
    assert "--select-video=res=1920*:frame=30*" in joined
    assert "--select-audio=all" in joined
    assert "--select-subtitle=all" in joined


def test_build_argv_defaults_to_best_variant(settings: SiphonSettings, tmp_path: Path):
    spec = FetchSpec(url="https://e/i.m3u8", title="demo", out_dir=str(tmp_path))
    assert "--select-video=best" in " ".join(build_argv("engine", spec, settings))


def test_build_argv_has_no_duplicate_tokens(settings: SiphonSettings, tmp_path: Path):
    spec = FetchSpec(url="https://e/i.m3u8", title="demo", out_dir=str(tmp_path))
    argv = build_argv("engine", spec, settings)
    assert len(argv) == len(set(argv))


def test_headers_and_referer(settings: SiphonSettings, tmp_path: Path):
    settings.extra_headers = "User-Agent: Foo\nCookie: a=b"
    settings.referer = "https://ref/"
    spec = FetchSpec(url="https://e/i.m3u8", title="demo", out_dir=str(tmp_path))
    argv = build_argv("engine", spec, settings)

    assert "--header=User-Agent: Foo" in argv
    assert "--header=Cookie: a=b" in argv
    assert "--header=Referer: https://ref/" in argv


def test_proxy_modes(settings: SiphonSettings, tmp_path: Path):
    spec = FetchSpec(url="https://e/i.m3u8", title="demo", out_dir=str(tmp_path))

    settings.proxy_mode = "none"
    assert "--use-system-proxy=false" in build_argv("engine", spec, settings)

    settings.proxy_mode = "system"
    assert "--use-system-proxy=true" in build_argv("engine", spec, settings)

    settings.proxy_mode = "manual"
    settings.manual_proxy = "http://127.0.0.1:7890"
    argv = build_argv("engine", spec, settings)
    assert "--custom-proxy=http://127.0.0.1:7890" in argv


def test_decrypt_engine_name_mapping(settings: SiphonSettings, tmp_path: Path):
    spec = FetchSpec(url="https://e/i.m3u8", title="demo", out_dir=str(tmp_path))

    settings.decrypt_engine = "ffmpeg"
    assert "--decryption-engine=FFmpeg" in build_argv("engine", spec, settings)

    settings.decrypt_engine = "shaka"
    assert "--decryption-engine=Shaka" in build_argv("engine", spec, settings)


def test_keep_temp_toggles_delete_flag(settings: SiphonSettings, tmp_path: Path):
    spec = FetchSpec(url="https://e/i.m3u8", title="demo", out_dir=str(tmp_path))

    settings.keep_temp = False
    assert "--del-after-done=true" in build_argv("engine", spec, settings)

    settings.keep_temp = True
    assert "--del-after-done=true" not in build_argv("engine", spec, settings)


def test_expected_suffixes_for_live_and_vod(settings: SiphonSettings, tmp_path: Path):
    vod = FetchSpec(url="u", title="t", out_dir=str(tmp_path))
    live = FetchSpec(url="u", title="t", out_dir=str(tmp_path), is_live=True)

    assert ".mp4" in expected_suffixes(vod, settings)
    assert ".ts" in expected_suffixes(live, settings)


def test_fetch_spec_requires_url(settings: SiphonSettings):
    with pytest.raises(ValueError):
        FetchSpec.from_payload({"url": "  "}, settings)


def test_fetch_spec_falls_back_to_default_dir(settings: SiphonSettings):
    spec = FetchSpec.from_payload({"url": "https://e/i.m3u8"}, settings)
    assert spec.out_dir == settings.output_dir


def test_job_store_roundtrip(tmp_path: Path):
    store = JobStore(tmp_path / "t.db")
    record = store.insert(source_url="https://e/i.m3u8", title="demo", variant="1280x720",
                          kind="vod", out_dir=str(tmp_path), file_hint="",
                          argv=["a", "b"], log_path="")
    assert record.argv == ["a", "b"]

    updated = store.update(record.job_id, status=STATUS_DONE, bytes_total=456)
    assert updated is not None and updated.status == STATUS_DONE
    assert updated.bytes_total == 456

    assert len(store.list(status=STATUS_DONE)) == 1
    assert store.list(status=STATUS_FAILED) == []

    store.delete(record.job_id)
    assert store.get(record.job_id) is None


def test_job_store_mark_orphans_failed(tmp_path: Path):
    store = JobStore(tmp_path / "t.db")
    first = store.insert(source_url="u1", title="a", variant="", kind="vod",
                         out_dir=str(tmp_path), file_hint="", argv=[], log_path="")
    second = store.insert(source_url="u2", title="b", variant="", kind="vod",
                          out_dir=str(tmp_path), file_hint="", argv=[], log_path="")
    store.update(first.job_id, status=STATUS_RUNNING)
    store.update(second.job_id, status=STATUS_DONE)

    assert store.mark_orphans_failed() == 1
    assert store.get(first.job_id).status == STATUS_FAILED
    assert store.get(second.job_id).status == STATUS_DONE


def test_settings_reject_unknown_keys(tmp_path: Path):
    from siphon.settings import SettingsStore

    store = SettingsStore(tmp_path / "s.json")
    result = store.replace({"not_a_field": 1, "parallel_fragments": 4})
    assert not hasattr(result, "not_a_field")
    assert result.parallel_fragments == 4


def test_settings_clamp_out_of_range(tmp_path: Path):
    from siphon.settings import SettingsStore

    store = SettingsStore(tmp_path / "s.json")
    result = store.replace({"parallel_fragments": 999, "request_timeout": 1,
                            "proxy_mode": "bogus"})
    assert result.parallel_fragments == 128
    assert result.request_timeout == 5
    assert result.proxy_mode == "system"


def test_settings_persist_to_disk(tmp_path: Path):
    from siphon.settings import SettingsStore

    path = tmp_path / "s.json"
    SettingsStore(path).replace({"accent": "#123456"})
    assert SettingsStore(path).read().accent == "#123456"
