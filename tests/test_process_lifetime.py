"""Real subprocess ownership at tool-stage boundaries; no FPGA device required."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX process-group contract')
SOURCE = Path(os.environ.get('SILICONPILOT_TEST_SOURCE', Path(__file__).resolve().parents[1])).resolve()
WORKER = r'''
from pathlib import Path
import os
import subprocess
import sys
import time
sys.path.insert(0, sys.argv[1]+'/src')
directory = Path(sys.argv[2])
role, timeout, leader_exits = sys.argv[3:]
tool = str(directory / 'tool')


class ReadyTool(subprocess.Popen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pid_file = directory / 'launch.tmp'
        pid_file.write_text(f'{self.pid} {os.getpgid(self.pid)}')
        pid_file.replace(directory / 'launch')

    def communicate(self, input=None, timeout=None):
        if not self._ready:
            self._ready = True
            deadline = time.monotonic() + 15
            while not (directory / 'pids.json').exists():
                if time.monotonic() >= deadline or self.poll() is not None:
                    raise RuntimeError('Tool did not report readiness')
                time.sleep(.01)
            if leader_exits == 'True':
                self.wait(timeout=15)
            (directory / 'communicating').touch()
        return super().communicate(input=input, timeout=timeout)

    _ready = False


# Keep the real subprocess timeout and cleanup. Only the fixture startup is gated.
subprocess.Popen = ReadyTool
if role=='toolchain':
    from siliconpilot.toolchain import _run
    _run([tool],directory,'stage.log',timeout=float(timeout))
elif role=='netlist':
    from siliconpilot.netlist import _run
    _run([tool],directory,'stage.log',timeout=float(timeout))
elif role=='verification':
    from siliconpilot.verification import _simulate
    _simulate(directory,'stage','module tb; endmodule',tool,tool)
elif role=='formal':
    from siliconpilot.formal import prove_tiny
    prove_tiny(directory)
'''


def live(pid):
    proc = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    return proc.returncode == 0 and bool(proc.stdout.strip()) and not proc.stdout.lstrip().startswith('Z')


@contextmanager
def launch(directory, role, timeout=30, *, leader_exits=False, close_pipes=False):
    directory.mkdir()
    script = directory / 'tool'
    script.write_text('#!' + sys.executable + '\n' + r'''
from pathlib import Path
import json,os,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],
                       stdout=subprocess.DEVNULL if CLOSE_PIPES else None,
                       stderr=subprocess.DEVNULL if CLOSE_PIPES else None)
print('live stdout diagnostic',flush=True)
print('live stderr diagnostic',file=sys.stderr,flush=True)
if CLOSE_PIPES:
    os.close(1)
    os.close(2)
Path('pids.tmp').write_text(json.dumps({'leader':os.getpid(),'child':child.pid}))
Path('pids.tmp').replace('pids.json')
if not LEADER_EXITS:
    time.sleep(60)
'''.replace('CLOSE_PIPES', repr(close_pipes)).replace('LEADER_EXITS', repr(leader_exits)))
    script.chmod(0o755)
    (directory / 'yosys').symlink_to(script)
    env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ.get('PATH', ''))
    host = subprocess.Popen(
        [sys.executable, '-c', WORKER, str(SOURCE), str(directory), role,
         str(timeout), str(leader_exits)],
        cwd=directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        ready = directory / 'communicating'
        deadline = time.monotonic() + 15
        while not ready.exists() and host.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists(), 'Stage did not reach the actual subprocess'
        yield host, json.loads((directory / 'pids.json').read_text())
    finally:
        try:
            os.killpg(host.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        registration = directory / 'launch'
        if registration.exists():
            leader, group = map(int, registration.read_text().split())
            if group == leader:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        host.communicate(timeout=15)


@pytest.mark.parametrize('role', ['toolchain', 'netlist'])
@pytest.mark.parametrize('leader_exits', [False, True])
def test_timeout_stops_descendant_and_keeps_diagnostic(tmp_path, role, leader_exits):
    directory = tmp_path / role
    with launch(directory, role, .5, leader_exits=leader_exits) as (host, pids):
        _, stderr = host.communicate(timeout=15)
        assert host.returncode != 0 and ('timed out' in stderr.lower() or 'exceeded' in stderr.lower())
        assert not live(pids['child']), 'Timed-out tool left its worker running'
        log = (directory / 'stage.log').read_text()
        assert 'live stdout diagnostic' in log and 'live stderr diagnostic' in log


@pytest.mark.parametrize('role', ['toolchain', 'netlist', 'verification', 'formal'])
def test_interrupt_stops_tool_and_descendant_without_touching_other_job(tmp_path, role):
    with subprocess.Popen(
        [sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True,
    ) as unrelated:
        try:
            with launch(tmp_path / role, role) as (host, pids):
                os.kill(host.pid, signal.SIGINT)
                host.communicate(timeout=15)
                assert host.returncode != 0
                assert not live(pids['leader']), 'Interrupted stage leader remains running'
                assert not live(pids['child']), 'Interrupted stage worker remains running'
                assert unrelated.poll() is None, 'Another invocation must remain independent'
        finally:
            unrelated.kill()


def test_closed_output_pipes_keep_timeout_diagnostic(tmp_path):
    directory = tmp_path / 'closed'
    with launch(directory, 'toolchain', .5, close_pipes=True) as (host, pids):
        host.communicate(timeout=15)
        assert host.returncode != 0
        assert not live(pids['child'])
        assert 'live stdout diagnostic' in (directory / 'stage.log').read_text()


def test_concurrent_tool_invocations_have_separate_lifetimes(tmp_path):
    with launch(tmp_path / 'second', 'toolchain') as (second, second_pids):
        with launch(tmp_path / 'first', 'netlist', .5) as (first, first_pids):
            first.communicate(timeout=15)
            assert not live(first_pids['child'])
            assert second.poll() is None
            assert live(second_pids['leader']) and live(second_pids['child'])
            os.kill(second.pid, signal.SIGINT)
            second.communicate(timeout=15)
            assert not live(second_pids['child'])


@pytest.mark.parametrize('role', ['toolchain', 'netlist'])
@pytest.mark.parametrize('exit_code', [0, 7])
def test_completed_commands_preserve_output_and_failure(tmp_path, role, exit_code):
    sys.path.insert(0, str(SOURCE / 'src'))
    from siliconpilot import netlist, toolchain

    module = {'toolchain': toolchain, 'netlist': netlist}[role]
    command = [sys.executable, '-c', f'import sys; print("out"); print("err",file=sys.stderr); sys.exit({exit_code})']
    if exit_code:
        with pytest.raises(RuntimeError, match=r'failed \(7\)'):
            module._run(command, tmp_path, 'stage.log', timeout=3)
    else:
        result = module._run(command, tmp_path, 'stage.log', timeout=3)
        assert result == 'out\nerr\n' if role == 'netlist' else result >= 0
    assert (tmp_path / 'stage.log').read_text() == 'out\nerr\n'
