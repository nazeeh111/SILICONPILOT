"""Own the lifetime of one synchronous external tool invocation."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess


def run_command(command: list[str], directory: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(command, cwd=directory, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True,
                               start_new_session=os.name == 'posix')
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException as error:
        # A leader can exit while its worker still holds the output pipes.
        # Keep the original session ID; the leader PID may no longer exist.
        try:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=1)
            if isinstance(error, subprocess.TimeoutExpired):
                error.output, error.stderr = stdout, stderr
        except (subprocess.TimeoutExpired, UnicodeError):
            # A process that deliberately leaves the session is outside this
            # ownership boundary. Do not wait indefinitely for its pipes.
            pass
        finally:
            process.wait()
        raise
    finally:
        process.stdout.close()
        process.stderr.close()
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def timeout_log(error: subprocess.TimeoutExpired) -> str:
    def text(value: str | bytes | None) -> str:
        return value.decode(errors='replace') if isinstance(value, bytes) else value or ''

    return text(error.output) + text(error.stderr) + '\n' + str(error)
