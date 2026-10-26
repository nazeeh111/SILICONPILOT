"""Logged, bounded open-toolchain builds. Report physical estimates honestly."""
from __future__ import annotations
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping
from .compiler import compile_model
from .model import HardwareConfig


def _run(command: list[str], directory: Path, log: str, timeout: int = 600) -> float:
    started = time.perf_counter()
    try:
        result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        (directory / log).write_text(str(exc))
        raise RuntimeError(f'{command[0]} exceeded {timeout}s; see {directory / log}') from exc
    (directory / log).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed ({result.returncode}); see {directory / log}')
    return time.perf_counter() - started


def require_tool(name: str) -> str:
    result = shutil.which(name)
    if not result:
        raise RuntimeError(f'{name} missing: install pinned OSS CAD Suite and add its bin directory to PATH')
    return result


def run_build(model: Mapping[str, Any], config: HardwareConfig, output_dir: str | Path,
              route: bool = True, clock_mhz: float = 25.0,
              reuse_synthesis: bool = False,
              time_budget_seconds: float | None = None) -> dict[str, Any]:
    if not 0 < clock_mhz <= 500:
        raise ValueError('clock_mhz must be in (0, 500]')
    if time_budget_seconds is not None and time_budget_seconds <= 0:
        raise ValueError('time_budget_seconds must be positive')
    started = time.perf_counter()
    directory = Path(output_dir).resolve()
    previous = None
    if reuse_synthesis and (directory / 'build.json').exists():
        previous = json.loads((directory / 'build.json').read_text())
    manifest = compile_model(model, config, directory)
    yosys = require_tool('yosys')
    script = 'read_verilog -sv design.v\nsynth_ecp5 -top siliconpilot_top -json synthesized.json\ntee -o synthesis-stat.json stat -json\nwrite_verilog -noattr synthesized.v\n'
    (directory / 'synth.ys').write_text(script)
    if previous and previous.get('rtl_sha256') == manifest['rtl_sha256'] and (directory/'synthesized.json').exists():
        expected = previous['artifacts']['synthesized.json']['sha256']
        if hashlib.sha256((directory/'synthesized.json').read_bytes()).hexdigest() != expected:
            raise ValueError('Saved synthesis artifact hash mismatch; refusing reuse')
        synth_seconds = previous['synthesis_seconds']
    else:
        if time_budget_seconds is not None and time.perf_counter()-started >= time_budget_seconds:
            raise RuntimeError('Budget exhausted before synthesis; generated HDL retained')
        synth_seconds = _run([yosys, '-s', 'synth.ys'], directory, 'synthesis.log')
    netlist = json.loads((directory / 'synthesized.json').read_text())
    counts: dict[str, int] = {}
    for cell in netlist['modules']['siliconpilot_top']['cells'].values():
        counts[cell['type']] = counts.get(cell['type'], 0) + 1
    report: dict[str, Any] = {
        'schema_version': 1, 'target': manifest['target'], 'clock_mhz': clock_mhz,
        'rtl_sha256': manifest['rtl_sha256'], 'model_sha256': manifest['model_sha256'],
        'config': config.to_dict(), 'dimensions': manifest['dimensions'],
        'lut': counts.get('LUT4', 0) + 2 * counts.get('CCU2C', 0),
        'logic_lut': counts.get('LUT4', 0), 'carry_lut': 2 * counts.get('CCU2C', 0),
        'lut_scope': 'Mapped LUT4 equivalents: logic LUT4 + 2 per CCU2C carry cell; mux primitives reported separately in cell_counts.',
        'ff': counts.get('TRELLIS_FF', 0),
        'dsp': counts.get('MULT18X18D', 0), 'bram': counts.get('DP16KD', 0),
        'cell_counts': counts, 'synthesis_seconds': synth_seconds,
        'route_seconds': 0.0, 'compile_seconds': synth_seconds, 'routed': False,
        'latency_cycles': manifest['latency_cycles'],
        'initiation_interval_cycles': manifest['initiation_interval_cycles'],
        'latency_us': manifest['latency_cycles'] / clock_mhz,
        'core_throughput_estimate_per_s': clock_mhz * 1e6 / manifest['initiation_interval_cycles'],
        'throughput_scope': 'Analytic core initiation-interval bound; excludes streaming-shell serialization, stalls, and physical IO.',
        'measurement_scope': 'core simulated cycle model; Yosys mapped cells; nextpnr device timing estimate when routed. No physical FPGA measurement.',
        'io_constraints': 'Unconstrained board pins auto-assigned by nextpnr; not a board-ready programming image. Clock constrained; external IO delays unspecified.',
        'tool_versions': {'yosys': subprocess.run([yosys, '-V'], text=True, capture_output=True).stdout.strip()},
        'commands': [[yosys, '-s', 'synth.ys']],
    }
    route_allowed = time_budget_seconds is None or time.perf_counter()-started < time_budget_seconds
    report['budget_exhausted_before_route'] = bool(route and not route_allowed)
    if route and route_allowed:
        nextpnr = require_tool('nextpnr-ecp5')
        (directory / 'constraints.lpf').write_text(f'# Device-level research build. Board pin assignment intentionally unspecified.\nFREQUENCY PORT "clk" {clock_mhz:g} MHz;\n')
        command = [nextpnr, '--25k', '--package', 'CABGA256', '--speed', '6',
                   '--json', 'synthesized.json', '--lpf', 'constraints.lpf',
                   '--lpf-allow-unconstrained', '--freq', str(clock_mhz), '--seed', '1',
                   '--textcfg', 'routed.config', '--report', 'routing.json', '--timing-allow-fail']
        route_seconds = _run(command, directory, 'routing.log')
        routing = json.loads((directory / 'routing.json').read_text())
        clocks = routing.get('fmax', {})
        frequencies = [value['achieved'] for value in clocks.values() if 'achieved' in value]
        fmax = min(frequencies) if frequencies else None
        report.update(route_seconds=route_seconds, compile_seconds=synth_seconds+route_seconds,
                      routed=True, fmax_mhz=fmax, timing_met=fmax is not None and fmax >= clock_mhz,
                      routing_utilization=routing.get('utilization', {}), timing_clocks=clocks,
                      routed_comb=routing.get('utilization',{}).get('TRELLIS_COMB',{}).get('used'))
        version = subprocess.run([nextpnr, '--version'], text=True, capture_output=True)
        report['tool_versions']['nextpnr'] = (version.stdout+version.stderr).strip()
        report['commands'].append(command)
    report['artifacts'] = {}
    for name in ['design.v','weights.json','manifest.json','synth.ys','synthesized.json','synthesized.v','synthesis.log','synthesis-stat.json','constraints.lpf','routing.json','routing.log','routed.config']:
        path = directory / name
        if path.exists():
            report['artifacts'][name] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (directory / 'build.json').write_text(json.dumps(report, indent=2)+'\n')
    return report
