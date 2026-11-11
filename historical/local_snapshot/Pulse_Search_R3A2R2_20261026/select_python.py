#!/usr/bin/env python3
"""Select an existing approved Linux Python for CPU-only PyTorch 2.6 research.

Read-only selection. Does not install interpreters or change system configuration.
The selected Python must support pip downloads and isolated venv+pip installation.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORTED = {(3, 10), (3, 11), (3, 12), (3, 13)}


def check(executable):
    """Return (resolved interpreter path, version) or raise ValueError."""
    resolved = shutil.which(executable) if not Path(executable).is_absolute() else executable
    if not resolved:
        raise ValueError('interpreter unavailable')
    try:
        p = subprocess.run(
            [resolved, '-B', '-c', 'import sys; print(sys.version_info.major, sys.version_info.minor, sys.platform)'],
            capture_output=True, text=True, timeout=10, check=True,
        )
        major, minor, platform = p.stdout.strip().split()
        ver = (int(major), int(minor))
        if ver not in SUPPORTED or platform != 'linux':
            raise ValueError(f'unsupported interpreter: {major}.{minor} {platform}')
        subprocess.run(
            [resolved, '-m', 'pip', '--version'],
            capture_output=True, text=True, timeout=10, check=True,
        )
        # Exercise the actual facility that provision.py later uses, *before* acquisition.
        with tempfile.TemporaryDirectory(prefix='pulse-search-r3a2-python-preflight-') as tmp:
            p = subprocess.run(
                [resolved, '-m', 'venv', str(Path(tmp) / 'env')],
                capture_output=True, text=True, timeout=55,
            )
            if p.returncode:
                raise ValueError('venv with pip not usable: ' + p.stderr.strip()[-300:])
        return os.path.abspath(resolved), f'{major}.{minor}'
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


def select():
    explicit = os.environ.get('PULSE_R3A2_PYTHON', '').strip()
    # An explicit owner-selected interpreter must pass; do not silently override it.
    if explicit:
        try:
            path, version = check(explicit)
        except ValueError as e:
            raise RuntimeError('HOLD_OWNER_SELECTED_PYTHON_NOT_USABLE: ' + str(e)) from e
        print(f'R3A2_SELECTED_PYTHON={path} (Python {version})', file=sys.stderr)
        return path

    candidates = [sys.executable, 'python3.13', 'python3.12', 'python3.11', 'python3.10']
    seen = set()
    reasons = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            path, version = check(candidate)
        except ValueError as e:
            reasons.append(f'{candidate}: {e}')
            continue
        print(f'R3A2_SELECTED_PYTHON={path} (Python {version})', file=sys.stderr)
        return path
    raise RuntimeError(
        'HOLD_NO_PYTHON_310_TO_313_WITH_PIP_AND_VENV. '
        'No model or dependency download started. '
        'Use an existing supported interpreter via PULSE_R3A2_PYTHON, or arrange '
        'an isolated Python 3.12 installation separately. Probes: ' + '; '.join(reasons)
    )


if __name__ == '__main__':
    try:
        print(select())
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
