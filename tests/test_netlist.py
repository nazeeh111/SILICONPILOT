"""Actual synthesis/netlist differential checks and evidence-integrity failures."""
import json
from pathlib import Path
import shutil
import pytest
from siliconpilot.model import HardwareConfig
from siliconpilot.verification import verify_model
from siliconpilot.toolchain import run_build
from siliconpilot.netlist import run_netlist_verification, prepare_logic_only_build

TOOLS = all(shutil.which(name) for name in ('yosys', 'iverilog', 'vvp'))


def test_requires_existing_build_and_verification(tmp_path):
    with pytest.raises(ValueError, match='Missing design.v'):
        run_netlist_verification(tmp_path)


def tiny_model():
    return {'name': 'mapped-carry-check', 'input_size': 1,
            'layers': [{'op': 'dense', 'weights': [[1.25]], 'bias': [-0.125]}]}


@pytest.mark.skipif(not TOOLS, reason='Yosys and Icarus required')
def test_exact_mapped_netlist_and_detects_corrupt_expected(tmp_path):
    cfg = HardwareConfig(bits=4, fractional_bits=2, accumulator_bits=8)
    verify_model(tiny_model(), cfg, tmp_path, random_count=12)
    build = prepare_logic_only_build(tmp_path, tmp_path/'logic')
    tmp_path = tmp_path/'logic'
    assert build['dsp'] == 0  # This case must exercise actual upstream modeled cells.
    result = run_netlist_verification(tmp_path)
    assert result['passed'] and result['mapped_simulation_passed']
    assert result['scope'] == 'exact mapped ECP5 netlist'
    assert result['backpressure_cycles'] > 0
    expected = tmp_path / 'expected.hex'
    rows = expected.read_text().splitlines()
    rows[0] = '0' if rows[0] != '0' else 'f'
    expected.write_text('\n'.join(rows) + '\n')
    with pytest.raises(RuntimeError, match='Netlist command failed'):
        run_netlist_verification(tmp_path)
    assert not json.loads((tmp_path / 'netlist-verification.json').read_text())['passed']


@pytest.mark.skipif(not TOOLS, reason='Yosys and Icarus required')
def test_rejects_changed_synthesis_artifact(tmp_path):
    cfg = HardwareConfig(bits=4, fractional_bits=2, accumulator_bits=8)
    verify_model(tiny_model(), cfg, tmp_path, random_count=0)
    run_build(tiny_model(), cfg, tmp_path, route=False)
    with (tmp_path / 'synthesized.v').open('a') as out:
        out.write('\n// tampered artifact\n')
    with pytest.raises(ValueError, match='synthesized.v hash differs'):
        run_netlist_verification(tmp_path)


@pytest.mark.skipif(not TOOLS, reason='Yosys and Icarus required')
def test_dsp_blackboxes_use_explicit_generic_synthesis_fallback(tmp_path):
    model = {'name': 'dsp-fallback', 'input_size': 2,
             'layers': [{'op': 'dense', 'weights': [[0.75, 1.25], [-1.25, 0.75]], 'bias': [0.125, -0.125]}]}
    cfg = HardwareConfig(bits=8, fractional_bits=4, accumulator_bits=16)
    verify_model(model, cfg, tmp_path, random_count=12)
    build = run_build(model, cfg, tmp_path, route=False)
    assert build['dsp'] > 0
    report = run_netlist_verification(tmp_path)
    assert report['passed']
    assert report['mapped_simulation_passed'] is None
    assert not report['mapped_simulation_available']
    assert 'MULT18X18D' in report['unsupported_mapped_primitives']
    assert report['generic_netlist_sha256']
    assert report['backpressure_cycles'] > 0
