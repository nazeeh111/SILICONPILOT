"""Differential post-synthesis simulation without inventing blackbox behavior.

Exact mapped ECP5 simulation is used only for the supported upstream behavioral
primitives. Designs containing e.g. MULT18X18D are explicitly marked unavailable
for that check and separately synthesized into generic gates for simulation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any

# These cells have executable upstream models in techlibs/ecp5/cells_sim.v
# and its included common_sim.vh and ccu2c_sim.vh. Never read cells_bb.v:
# blackboxes with undriven outputs are not functional models.
BEHAVIORAL_PRIMITIVES = frozenset({"LUT4", "PFUMX", "L6MUX21", "CCU2C", "TRELLIS_FF"})


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str], directory: Path, log: str, timeout: int = 240) -> str:
    try:
        result = subprocess.run(command, cwd=directory, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        (directory / log).write_text(str(exc))
        raise RuntimeError(f"Netlist verification timed out; see {directory / log}") from exc
    output = result.stdout + result.stderr
    (directory / log).write_text(output)
    if result.returncode:
        raise RuntimeError(f"Netlist command failed ({result.returncode}); see {directory / log}")
    return output


def _datadir(yosys: str) -> Path:
    config = Path(yosys).with_name("yosys-config")
    if config.exists():
        result = subprocess.run([str(config), "--datdir"], capture_output=True, text=True)
        if result.returncode == 0:
            candidate = Path(result.stdout.strip())
            if (candidate / "ecp5/cells_sim.v").exists():
                return candidate
    candidate = Path(yosys).resolve().parent.parent / "share/yosys"
    if not (candidate / "ecp5/cells_sim.v").exists():
        raise RuntimeError("Cannot locate Yosys ECP5 behavioral library; pass yosys_datadir explicitly")
    return candidate


def run_netlist_verification(directory: str | Path, *, yosys_datadir: str | Path | None = None) -> dict[str, Any]:
    """Verify saved synthesis against the saved independent integer test vectors.

    First run build and verify into the same directory. This check requires
    design.v, synthesized.v/json, build.json, verification.json, manifest.json,
    tb_streaming.v, inputs.hex and expected.hex. It does not regenerate expected
    outputs from RTL or overwrite the build/RTL verification evidence.
    """
    directory = Path(directory).resolve()
    required = ("design.v", "synthesized.v", "synthesized.json", "build.json", "verification.json", "manifest.json", "tb_streaming.v", "inputs.hex", "expected.hex")
    for name in required:
        if not (directory / name).is_file():
            raise ValueError(f"Missing {name}; build and independently verify into the same directory first")
    build = json.loads((directory / "build.json").read_text())
    verification = json.loads((directory / "verification.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    rtl_hash = _hash(directory / "design.v")
    if not verification.get("passed") or not verification.get("results", {}).get("streaming", {}).get("passed"):
        raise ValueError("Requires passing independent streaming RTL verification")
    if any(report.get("rtl_sha256") != rtl_hash for report in (build, verification, manifest)):
        raise ValueError("Build, verification and manifest must refer to the exact saved RTL")
    for name in ("synthesized.json", "synthesized.v"):
        expected_hash = build.get("artifacts", {}).get(name, {}).get("sha256")
        if not expected_hash or expected_hash != _hash(directory / name):
            raise ValueError(f"Saved {name} hash differs from build evidence")
    tools = {name: shutil.which(name) for name in ("yosys", "iverilog", "vvp")}
    if not all(tools.values()):
        raise RuntimeError("Post-synthesis verification requires yosys, iverilog and vvp on PATH")
    yosys, iverilog, vvp = (str(tools[name]) for name in ("yosys", "iverilog", "vvp"))
    cells = json.loads((directory / "synthesized.json").read_text())["modules"]["siliconpilot_top"]["cells"]
    cell_types = {cell["type"] for cell in cells.values()} - {"$scopeinfo"}
    unsupported = sorted(cell_types - BEHAVIORAL_PRIMITIVES)
    report: dict[str, Any] = {
        "schema_version": 1, "passed": False, "rtl_sha256": rtl_hash,
        "expected_sha256": _hash(directory / "expected.hex"), "inputs_sha256": _hash(directory / "inputs.hex"),
        "testbench_sha256": _hash(directory / "tb_streaming.v"),
        "mapped_netlist_sha256": _hash(directory / "synthesized.v"),
        "samples": verification["samples"], "mapped_simulation_available": not unsupported,
        "unsupported_mapped_primitives": unsupported,
        "limitations": "Zero-delay digital functional simulation; no routed delays, IO electrical validation, physical FPGA measurement, or arbitrary-input equivalence proof.",
        "commands": [],
    }
    # A separate working directory preserves previous RTL logs and waveforms.
    sim = directory / "netlist-check"
    sim.mkdir(exist_ok=True)
    for name in ("tb_streaming.v", "inputs.hex", "expected.hex"):
        shutil.copyfile(directory / name, sim / name)
    # RTL waveforms are retained by verify_model. Dumping every mapped gate can
    # otherwise dominate disk/runtime without improving this bit comparison.
    tb = (sim / "tb_streaming.v").read_text()
    tb = re.sub(r'\$dumpfile\([^;]*\);\s*\$dumpvars\([^;]*\);', '// Gate-level waveform dump omitted; original RTL waveform retained.', tb)
    tb = tb.replace('$dumpoff;', ';')
    (sim / "tb_streaming.v").write_text(tb)
    report["simulation_testbench_sha256"] = _hash(sim / "tb_streaming.v")
    report["testbench_adapter"] = "Only waveform dump calls removed; stimulus and comparison unchanged"
    if not unsupported:
        share = Path(yosys_datadir).resolve() if yosys_datadir is not None else _datadir(yosys)
        library = share / "ecp5/cells_sim.v"
        if not library.is_file():
            raise ValueError(f"Missing ECP5 behavioral library {library}")
        source = directory / "synthesized.v"
        command = [iverilog, "-g2012", "-s", "tb", "-I", str(library.parent), "-o", "simulation", str(library), str(source), "tb_streaming.v"]
        report.update(scope="exact mapped ECP5 netlist", mapped_simulation_passed=False)
        report["behavioral_libraries"] = {p.name: _hash(p) for p in (library.parent / name for name in ("cells_sim.v", "common_sim.vh", "ccu2c_sim.vh", "cells_ff.vh", "cells_io.vh")) if p.is_file()}
    else:
        # Yosys's ECP5 DSP declaration is a blackbox in the pinned toolchain.
        # Generic synthesis verifies a different, explicitly identified netlist.
        script = "read_verilog -sv ../design.v\nsynth -top siliconpilot_top\nwrite_verilog -noattr generic-synthesized.v\n"
        (sim / "generic-synth.ys").write_text(script)
        synth_command = [yosys, "-s", "generic-synth.ys"]
        report["commands"].append(synth_command)
        _run(synth_command, sim, "generic-synthesis.log")
        source = sim / "generic-synthesized.v"
        command = [iverilog, "-g2012", "-s", "tb", "-o", "simulation", str(source), "tb_streaming.v"]
        report.update(scope="separately synthesized generic gates; mapped ECP5 simulation unavailable", mapped_simulation_passed=None,
                      generic_netlist_sha256=_hash(source), generic_simulation_passed=False,
                      mapped_limitation="No trusted behavioral model for " + ", ".join(unsupported) + "; blackboxes were not treated as simulated hardware.")
    report["commands"].append(command)
    try:
        _run(command, sim, "netlist-compile.log")
        run_command = [vvp, "simulation"]
        report["commands"].append(run_command)
        log = _run(run_command, sim, "netlist-simulation.log")
        match = re.search(r"PASS samples=(\d+) cycles=(\d+) stalls=(\d+) first_latency=(-?\d+)", log)
        if not match or int(match[1]) != verification["samples"]:
            raise RuntimeError("Netlist simulation did not produce complete matching sample evidence")
        report.update(passed=True, simulation_cycles=int(match[2]), backpressure_cycles=int(match[3]), first_latency_cycles=int(match[4]))
        if not unsupported:
            report["mapped_simulation_passed"] = True
        else:
            report["generic_simulation_passed"] = True
    finally:
        report["tool_versions"] = {
            "yosys": subprocess.run([yosys, "-V"], capture_output=True, text=True).stdout.strip(),
            "iverilog": subprocess.run([iverilog, "-V"], capture_output=True, text=True).stdout.splitlines()[0],
        }
        (directory / "netlist-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report



def prepare_logic_only_build(source_directory: str | Path, output_directory: str | Path, *, route: bool = False, clock_mhz: float = 25.0) -> dict[str, Any]:
    """Build a separate ECP5 LUT/carry variant, preserving the original DSP build.

    Yosys's documented -nodsp option implements multiplication in logic. This is
    a different mapped implementation, with its own utilization/timing evidence.
    """
    source_directory, directory = Path(source_directory).resolve(), Path(output_directory).resolve()
    if not 0 < clock_mhz <= 500:
        raise ValueError("clock_mhz must be in (0, 500]")
    yosys = shutil.which("yosys")
    if not yosys:
        raise RuntimeError("Logic-only synthesis requires yosys")
    required = ("design.v", "manifest.json", "verification.json", "tb_streaming.v", "inputs.hex", "expected.hex")
    for name in required:
        if not (source_directory / name).is_file():
            raise ValueError(f"Missing source evidence {name}")
    directory.mkdir(parents=True, exist_ok=False)
    for name in (*required, "weights.json"):
        if (source_directory / name).exists():
            shutil.copyfile(source_directory / name, directory / name)
    manifest = json.loads((directory / "manifest.json").read_text())
    script = "read_verilog -sv design.v\nsynth_ecp5 -nodsp -top siliconpilot_top -json synthesized.json\nwrite_verilog -noattr synthesized.v\n"
    (directory / "synth.ys").write_text(script)
    command = [yosys, "-s", "synth.ys"]
    start = time.perf_counter()
    _run(command, directory, "synthesis.log")
    synth_seconds = time.perf_counter() - start
    netlist = json.loads((directory / "synthesized.json").read_text())
    counts: dict[str, int] = {}
    for cell in netlist["modules"]["siliconpilot_top"]["cells"].values():
        counts[cell["type"]] = counts.get(cell["type"], 0) + 1
    report: dict[str, Any] = {
        "schema_version": 1, "rtl_sha256": _hash(directory / "design.v"),
        "mapping_policy": "synth_ecp5 -nodsp; multipliers implemented in LUT/carry logic",
        "model_sha256": manifest["model_sha256"], "target": manifest["target"], "config": manifest["config"],
        "dimensions": manifest["dimensions"], "clock_mhz": clock_mhz,
        "cell_counts": counts, "lut": counts.get("LUT4", 0) + 2 * counts.get("CCU2C", 0),
        "logic_lut": counts.get("LUT4", 0), "carry_lut": 2 * counts.get("CCU2C", 0),
        "lut_scope": "Mapped LUT4 equivalents: logic LUT4 + 2 per carry cell; mux packing separate",
        "ff": counts.get("TRELLIS_FF", 0), "dsp": counts.get("MULT18X18D", 0), "bram": counts.get("DP16KD", 0),
        "synthesis_seconds": synth_seconds, "route_seconds": 0.0, "compile_seconds": synth_seconds,
        "routed": False, "commands": [command],
        "latency_cycles": manifest["latency_cycles"], "latency_scope": manifest["latency_scope"],
        "measurement_scope": "Independent mapped digital functional simulation recorded separately; synthesis/routing estimates, no physical FPGA measurement.",
        "tool_versions": {"yosys": subprocess.run([yosys, "-V"], capture_output=True, text=True).stdout.strip()},
    }
    if report["dsp"]:
        raise RuntimeError("-nodsp synthesis unexpectedly produced DSP cells")
    if route:
        nextpnr = shutil.which("nextpnr-ecp5")
        if not nextpnr:
            raise RuntimeError("Routing requires nextpnr-ecp5")
        (directory / "constraints.lpf").write_text(f'# Device-level research route; auto-assigned pins; external IO delays unspecified.\nFREQUENCY PORT "clk" {clock_mhz:g} MHz;\n')
        route_command = [nextpnr, "--25k", "--package", "CABGA256", "--speed", "6", "--json", "synthesized.json", "--lpf", "constraints.lpf", "--lpf-allow-unconstrained", "--freq", str(clock_mhz), "--seed", "1", "--textcfg", "routed.config", "--report", "routing.json", "--timing-allow-fail"]
        start = time.perf_counter()
        _run(route_command, directory, "routing.log")
        route_seconds = time.perf_counter() - start
        timing = json.loads((directory / "routing.json").read_text())
        fmax = min((v["achieved"] for v in timing.get("fmax", {}).values() if "achieved" in v), default=None)
        report.update(routed=True, route_seconds=route_seconds, compile_seconds=synth_seconds + route_seconds,
                      fmax_mhz=fmax, timing_met=fmax is not None and fmax >= clock_mhz,
                      routing_utilization=timing.get("utilization", {}), timing_clocks=timing.get("fmax", {}),
                      io_constraints="Auto-assigned physical pins, clock frequency constrained, external IO delays unspecified; not board-ready")
        report["commands"].append(route_command)
        version = subprocess.run([nextpnr, "--version"], capture_output=True, text=True)
        report["tool_versions"]["nextpnr"] = (version.stdout + version.stderr).strip()
    report["artifacts"] = {name: {"sha256": _hash(directory / name), "bytes": (directory / name).stat().st_size} for name in
                           ("design.v", "manifest.json", "synth.ys", "synthesized.json", "synthesized.v", "synthesis.log", "routing.json", "routing.log", "routed.config", "constraints.lpf") if (directory / name).exists()}
    (directory / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    return report

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--yosys-datadir", type=Path)
    parser.add_argument("--logic-only-from", type=Path, help="Create a new separate -nodsp ECP5 build from existing verified RTL")
    parser.add_argument("--route", action="store_true", help="Route the separate logic-only build")
    args = parser.parse_args()
    if args.logic_only_from is not None:
        prepare_logic_only_build(args.logic_only_from, args.directory, route=args.route)
    print(json.dumps(run_netlist_verification(args.directory, yosys_datadir=args.yosys_datadir), indent=2))


if __name__ == "__main__":
    main()
