"""Exercise Explorer-style CMD entry points without starting game services."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows CMD launcher')
ROOT = Path(__file__).resolve().parents[2]


def checkout(tmp_path, action, menu=True):
    root = tmp_path / 'HealthMon \ud300\uc6d0 (USB) & test!'
    root.mkdir()
    launcher = root / (action + '-HealthMon.cmd')
    shutil.copy2(ROOT / launcher.name, launcher)
    if menu:
        script = root / 'Server/scripts/runtime_menu.ps1'
        script.parent.mkdir(parents=True)
        shutil.copy2(ROOT / 'Server/scripts/runtime_menu.ps1', script)
    return launcher


def process(launcher, arguments='-NoPause', env=None):
    command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{launcher}" {arguments}"'
    return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                            env=env, creationflags=subprocess.CREATE_NO_WINDOW)


@pytest.mark.parametrize('action', ['Start', 'Stop'])
def test_menu_opens_without_powershell_in_path(tmp_path, action):
    launcher = checkout(tmp_path, action)
    with process(launcher, env=dict(os.environ, PATH='')) as child:
        stdout, stderr = child.communicate('0\n', timeout=15)
        assert child.returncode == 0, stdout + stderr
        assert '1. All (Backend + AI)' in stdout


@pytest.mark.parametrize('action', ['Start', 'Stop'])
def test_incomplete_zip_reports_missing_file(tmp_path, action):
    launcher = checkout(tmp_path, action, menu=False)
    with process(launcher) as child:
        stdout, stderr = child.communicate(timeout=15)
        assert child.returncode == 2, stdout + stderr
        assert 'Required menu script is missing' in stdout
        assert 'Extract the ENTIRE develop ZIP' in stdout


def test_double_click_failure_waits_for_acknowledgement(tmp_path):
    launcher = checkout(tmp_path, 'Start', menu=False)
    with process(launcher, arguments='') as child:
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                child.wait(timeout=1)
        finally:
            stdout, stderr = child.communicate('x\n', timeout=10)
        assert child.returncode == 2, stdout + stderr
        assert 'Required menu script is missing' in stdout


@pytest.mark.parametrize('failure', ['parse', 'parameter'])
def test_powershell_failure_before_menu_is_reported(tmp_path, failure):
    launcher = checkout(tmp_path, 'Start')
    arguments = '-NoPause'
    if failure == 'parse':
        (launcher.parent / 'Server/scripts/runtime_menu.ps1').write_text('param(\n', encoding='utf-8')
    else:
        arguments += ' -Target invalid'
    with process(launcher, arguments) as child:
        stdout, stderr = child.communicate(timeout=15)
        assert child.returncode != 0
        assert '[ERROR] HealthMon could not complete' in stdout, stdout + stderr


def test_service_exit_code_is_preserved(tmp_path):
    launcher = checkout(tmp_path, 'Start')
    stub = launcher.parent / 'Server/team/runtime.ps1'
    stub.parent.mkdir(parents=True)
    stub.write_text('exit 7\n', encoding='utf-8')
    with process(launcher, '-NoPause -Target Backend') as child:
        stdout, stderr = child.communicate(timeout=15)
        assert child.returncode == 7, stdout + stderr
        assert 'Exit code: 7' in stdout
