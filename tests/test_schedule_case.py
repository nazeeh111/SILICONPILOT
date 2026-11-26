"""Keep the public schedule comparison tied to the retained execution."""
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "docs" / "presentation"
OBSERVATORY = ROOT / "observatory"


def test_observatory_schedule_uses_exact_verified_circuits():
    execution = json.loads((PRESENTATION / "execution.json").read_text())
    bundle = PRESENTATION / "compiled-example.zip"
    source = OBSERVATORY / "data" / "schedule-case"
    assert hashlib.sha256(bundle.read_bytes()).hexdigest() == execution["bundleSHA256"]
    with ZipFile(bundle) as archive:
        for name in ("LICENSE", "THIRD_PARTY.md"):
            assert (source / name).read_bytes() == archive.read(name)
        for design, case in execution["cases"].items():
            name = f"{design}/design.v"
            hdl = (source / name).read_bytes()
            assert hdl == archive.read(name)
            assert hashlib.sha256(hdl).hexdigest() == case["manifest"]["rtl_sha256"]
            assert case["verification"]["rtl_sha256"] == case["manifest"]["rtl_sha256"]


def test_observatory_schedule_reports_the_recorded_core_counts():
    execution = json.loads((PRESENTATION / "execution.json").read_text())
    html = (OBSERVATORY / "index.html").read_text()
    assert {case["verification"]["samples"] for case in execution["cases"].values()} == {78}
    assert "78 synthetic vectors in core and serial-shell RTL simulation" in html
    for design, case in execution["cases"].items():
        manifest = case["manifest"]
        recorded = case["verification"]["results"]["schedule"]
        first, last = manifest["stage_compute_cycles"]
        handoff = recorded["latency_cycles"] - first - last
        row_start = html.index(f'data-design="{design}"')
        row_end = html.index("</dl>", row_start)
        row = html[row_start:row_end]
        assert f'--first: {first}; --handoff: {handoff}; --last: {last}' in row
        values = {
            "first": str(first),
            "handoff": str(handoff),
            "last": str(last),
            "latency": f'{recorded["latency_cycles"]} clocks',
            "interval": f'{recorded["initiation_interval_cycles"]} clocks',
        }
        assert dict(re.findall(r'data-measure="(\w+)">([^<]+)', row)) == values
