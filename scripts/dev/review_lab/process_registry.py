from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Mapping


@dataclass
class ManagedProcessRecord:
    name: str
    pid: int
    pgid: int
    command: list[str]
    stdout_log: str | None
    stderr_log: str | None
    running: bool = True


class ReviewProcessRegistry:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.registry_path = run_dir / 'process-registry.json'
        self._records: list[ManagedProcessRecord] = []
        self._processes: list[subprocess.Popen[str]] = []
        self._write_registry()

    def start(
        self,
        name: str,
        command: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        stdout_log_name: str,
        stderr_log_name: str,
    ) -> subprocess.Popen[str]:
        stdout_path = self.run_dir / stdout_log_name
        stderr_path = self.run_dir / stderr_log_name
        stdout_handle = stdout_path.open('w', encoding='utf-8')
        stderr_handle = stderr_path.open('w', encoding='utf-8')
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env={**os.environ, **dict(env)},
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            preexec_fn=os.setsid,
        )
        record = ManagedProcessRecord(
            name=name,
            pid=process.pid,
            pgid=os.getpgid(process.pid),
            command=command,
            stdout_log=stdout_log_name,
            stderr_log=stderr_log_name,
        )
        self._records.append(record)
        self._processes.append(process)
        self._write_registry()
        return process

    def stop_all(self, *, grace_seconds: int = 5) -> None:
        for process, record in reversed(list(zip(self._processes, self._records))):
            if process.poll() is not None:
                record.running = False
                continue
            try:
                os.killpg(record.pgid, signal.SIGTERM)
            except ProcessLookupError:
                record.running = False
                continue
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            if all(process.poll() is not None for process in self._processes):
                break
            time.sleep(0.2)
        for process, record in reversed(list(zip(self._processes, self._records))):
            if process.poll() is None:
                try:
                    os.killpg(record.pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            record.running = process.poll() is None
        self._write_registry()

    def safe_diagnostics(self) -> dict[str, object]:
        return {
            'processes': [asdict(record) for record in self._records],
        }

    def _write_registry(self) -> None:
        payload = {'processes': [asdict(record) for record in self._records]}
        self.registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
