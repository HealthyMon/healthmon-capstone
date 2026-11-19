"""Exercise the Windows menu in a disposable checkout, never the live services."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows launcher')
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def launcher(tmp_path):
    root = tmp_path / 'checkout with spaces'
    script = root / 'Server/scripts/runtime_menu.ps1'
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / 'Server/scripts/runtime_menu.ps1', script)
    for name in ('Server/scripts/local_server.ps1', 'Ai/Pose/android-device.ps1', 'Ai/Pose/pose-runtime.ps1'):
        stub = root / name
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("@{script=$MyInvocation.MyCommand.Name;arguments=@($args)} | ConvertTo-Json -Compress | "
                        "Set-Content -LiteralPath $env:HEALTHMON_MENU_TEST_OUTPUT -Encoding UTF8\n"
                        "exit ([int]$env:HEALTHMON_MENU_TEST_EXIT)\n", encoding='utf-8')
    output = tmp_path / 'invocation.json'

    def invoke(action, target=None, extra=(), stdin=None, code=0):
        args = ['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                '-Action', action, '-NoPause']
        if target is not None:
            args += ['-Target', target]
        result = subprocess.run(args + list(extra), input=stdin, capture_output=True, text=True,
                                env=dict(os.environ, HEALTHMON_MENU_TEST_OUTPUT=str(output), HEALTHMON_MENU_TEST_EXIT=str(code)),
                                timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        called = json.loads(output.read_text(encoding='utf-8-sig')) if output.exists() else None
        return result.returncode, called
    return invoke


@pytest.mark.parametrize('action', ['Start', 'Stop'])
@pytest.mark.parametrize('target', ['All', 'Backend', 'AI'])
def test_server_groups_remain_separate(launcher, action, target):
    code, call = launcher(action, target, ['-NoOpen'])
    assert code == 0
    assert call == {'script': 'local_server.ps1', 'arguments': ['-Action', action, '-Target', target, '-NoOpen']}


@pytest.mark.parametrize('action, expected', [('Start', 'connect'), ('Stop', 'disconnect')])
def test_android_preserves_device_arguments(launcher, action, expected):
    code, call = launcher(action, 'Android', ['-Serial', 'device-123', '-AdbPath', r'C:\SDK folder\adb.exe'])
    assert code == 0
    assert call == {'script': 'android-device.ps1', 'arguments': ['-Action', expected, '-Serial', 'device-123', '-AdbPath', r'C:\SDK folder\adb.exe']}


def test_setup_only_starts_from_start_menu(launcher):
    code, call = launcher('Stop', 'Setup')
    assert code != 0 and call is None
    code, call = launcher('Start', 'Setup')
    assert code == 0 and call == {'script': 'pose-runtime.ps1', 'arguments': ['-Action', 'setup']}


def test_service_failure_is_not_reported_as_success(launcher):
    code, call = launcher('Start', 'AI', code=7)
    assert call is not None and code == 7


def test_cancel_and_invalid_target_do_not_launch_anything(launcher):
    code, call = launcher('Start', stdin='0\n')
    assert code == 0 and call is None
    code, call = launcher('Start', 'unknown')
    assert code != 0 and call is None


def test_menu_selection_routes_backend(launcher):
    code, call = launcher('Start', stdin='2\n')
    assert code == 0 and call['arguments'] == ['-Action', 'Start', '-Target', 'Backend']
