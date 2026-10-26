"""Actual tool-stage budget behavior, rather than another arithmetic test."""
import shutil
import pytest
from siliconpilot.model import HardwareConfig
from siliconpilot.toolchain import run_build

TINY={'input_size':1,'layers':[{'op':'dense','weights':[[.5]],'bias':[0.]}]}


@pytest.mark.skipif(not shutil.which('yosys'),reason='Yosys is required')
def test_expired_preparation_budget_never_starts_synthesis(tmp_path):
    with pytest.raises(RuntimeError,match='Budget exhausted before synthesis'):
        run_build(TINY,HardwareConfig(),tmp_path,time_budget_seconds=1e-12)
    assert (tmp_path/'design.v').exists()
    assert not (tmp_path/'synthesis.log').exists()


@pytest.mark.skipif(not shutil.which('yosys'),reason='Yosys is required')
def test_synthesis_overrun_preserves_result_without_launching_route(tmp_path):
    report=run_build(TINY,HardwareConfig(),tmp_path,time_budget_seconds=.1)
    assert report['budget_exhausted_before_route']
    assert not report['routed']
    assert report['synthesis_seconds']>.1
    assert (tmp_path/'synthesized.json').exists()
    assert not (tmp_path/'routing.log').exists()
