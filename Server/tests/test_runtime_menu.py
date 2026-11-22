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
    for name in ('Server/scripts/local_server.ps1', 'Ai/Pose/android-device.ps1',
                 'Server/portable/setup.ps1', 'Server/portable/runtime.ps1'):
        stub = root / name
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("@{script=$MyInvocation.MyCommand.Name;arguments=@($args)} | ConvertTo-Json -Compress | "
                        "Add-Content -LiteralPath $env:HEALTHMON_MENU_TEST_OUTPUT -Encoding UTF8\n"
                        "if ($MyInvocation.MyCommand.Name -eq 'android-device.ps1') { exit ([int]$env:HEALTHMON_MENU_USB_EXIT) }\n"
                        "exit ([int]$env:HEALTHMON_MENU_TEST_EXIT)\n", encoding='utf-8')
    output = tmp_path / 'invocation.json'

    def invoke(action, target=None, extra=(), stdin=None, code=0, usb_code=0, portable=False):
        output.unlink(missing_ok=True)
        marker = root / '.runtime/portable/enabled'
        if portable:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text('portable-v1')
        else:
            marker.unlink(missing_ok=True)
        args = ['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                '-Action', action, '-NoPause']
        if target is not None:
            args += ['-Target', target]
        result = subprocess.run(args + list(extra), input=stdin, capture_output=True, text=True,
                                env=dict(os.environ, HEALTHMON_MENU_TEST_OUTPUT=str(output), HEALTHMON_MENU_TEST_EXIT=str(code),
                                         HEALTHMON_MENU_USB_EXIT=str(usb_code)),
                                timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        called = [json.loads(line.lstrip('\ufeff')) for line in output.read_text(encoding='utf-8-sig').splitlines() if line] if output.exists() else []
        return result.returncode, called
    return invoke


@pytest.mark.parametrize('action', ['Start', 'Stop'])
@pytest.mark.parametrize('target', ['All', 'Backend', 'AI'])
@pytest.mark.parametrize('portable', [False, True])
def test_server_groups_remain_separate(launcher, action, target, portable):
    code, calls = launcher(action, target, ['-NoOpen'], portable=portable)
    assert code == 0
    expected = [{'script': 'runtime.ps1' if portable else 'local_server.ps1',
                 'arguments': ['-Action', action, '-Target', target, '-NoOpen']}]
    if action == 'Start':
        expected.append({'script': 'android-device.ps1', 'arguments': ['-Action', 'connect', '-Auto']})
    assert calls == expected


@pytest.mark.parametrize('action, expected', [('Start', 'connect'), ('Stop', 'disconnect')])
def test_android_preserves_device_arguments(launcher, action, expected):
    code, call = launcher(action, 'Android', ['-Serial', 'device-123', '-AdbPath', r'C:\SDK folder\adb.exe'])
    assert code == 0
    assert call == [{'script': 'android-device.ps1', 'arguments': ['-Action', expected, '-Serial', 'device-123', '-AdbPath', r'C:\SDK folder\adb.exe']}]


def test_setup_only_starts_from_start_menu(launcher):
    code, call = launcher('Stop', 'Setup')
    assert code != 0 and not call
    code, call = launcher('Start', 'Setup', ['-BundlePath', r'D:\Team files\adapters.zip'])
    assert code == 0 and call == [{'script': 'setup.ps1', 'arguments': ['-BundlePath', r'D:\Team files\adapters.zip']}]


def test_service_failure_is_not_reported_as_success(launcher):
    code, call = launcher('Start', 'AI', code=7)
    assert len(call) == 1 and call[0]['script'] == 'local_server.ps1' and code == 7


def test_missing_android_does_not_fail_ready_pc_services(launcher):
    code, calls = launcher('Start', 'Backend', usb_code=7)
    assert code == 0 and [c['script'] for c in calls] == ['local_server.ps1', 'android-device.ps1']


def test_cancel_and_invalid_target_do_not_launch_anything(launcher):
    code, call = launcher('Start', stdin='0\n')
    assert code == 0 and not call
    code, call = launcher('Start', 'unknown')
    assert code != 0 and not call


def test_menu_selection_routes_backend(launcher):
    code, call = launcher('Start', stdin='2\n')
    assert code == 0 and call[0]['arguments'] == ['-Action', 'Start', '-Target', 'Backend', '-NoOpen']
