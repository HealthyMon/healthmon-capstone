"""Run the actual Windows menu in a disposable checkout; no live services."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows launcher')
ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def launcher(tmp_path):
    root = tmp_path / 'checkout with spaces'
    script = root / 'Server/scripts/runtime_menu.ps1'
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / 'Server/scripts/runtime_menu.ps1', script)
    for name in ('Server/team/runtime.ps1', 'Server/team/setup.ps1', 'Ai/Pose/android-device.ps1'):
        stub = root / name
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("@{script=$MyInvocation.MyCommand.Name;arguments=@($args)} | ConvertTo-Json -Compress | Add-Content -LiteralPath $env:HEALTHMON_MENU_TEST_OUTPUT -Encoding UTF8\n"
                        "if ($MyInvocation.MyCommand.Name -eq 'android-device.ps1') { exit ([int]$env:HEALTHMON_MENU_USB_EXIT) }\n"
                        "exit ([int]$env:HEALTHMON_MENU_TEST_EXIT)\n", encoding='utf-8')
    output = tmp_path / 'calls.json'
    def invoke(action, target=None, extra=(), stdin=None, code=0, usb_code=0):
        output.unlink(missing_ok=True)
        args = ['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Action',action,'-NoPause']
        if target:
            args += ['-Target',target]
        result = subprocess.run(args+list(extra), input=stdin, capture_output=True, text=True,
             env=dict(os.environ,HEALTHMON_MENU_TEST_OUTPUT=str(output),HEALTHMON_MENU_TEST_EXIT=str(code),HEALTHMON_MENU_USB_EXIT=str(usb_code)),
             timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
        if action == 'Start' and code == 0 and (target in ('All','Backend','AI') or (stdin or '').strip() in ('1','2','3')):
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                if output.exists() and len(output.read_text(encoding='utf-8-sig').splitlines())>=2:break
                time.sleep(.05)
        calls = [json.loads(line.lstrip('\ufeff')) for line in output.read_text(encoding='utf-8-sig').splitlines() if line] if output.exists() else []
        return result.returncode, calls
    return invoke

@pytest.mark.parametrize('action',['Start','Stop'])
@pytest.mark.parametrize('target',['All','Backend','AI'])
def test_groups_remain_independent_without_implicit_install(launcher,action,target):
    code,calls=launcher(action,target,['-NoOpen'])
    expected=[dict(script='runtime.ps1',arguments=['-Action',action,'-Target',target,'-NoOpen'])]
    if action=='Start':
        expected.append(dict(script='android-device.ps1',arguments=['-Action','connect','-Auto']))
    assert code==0 and calls==expected

@pytest.mark.parametrize('choice,target',[('1','All'),('2','Backend'),('3','AI'),('5','Setup')])
def test_numbered_menu(launcher,choice,target):
    code,calls=launcher('Start',stdin=choice+'\n')
    assert code==0
    if target=='Setup':
        assert calls==[dict(script='setup.ps1',arguments=[])]
    else:
        assert calls[0]==dict(script='runtime.ps1',arguments=['-Action','Start','-Target',target,'-NoOpen'])

@pytest.mark.parametrize('action,operation',[('Start','connect'),('Stop','disconnect')])
def test_android_arguments(launcher,action,operation):
    code,calls=launcher(action,'Android',['-Serial','phone','-AdbPath',r'C:\SDK folder\adb.exe'])
    assert code==0 and calls==[dict(script='android-device.ps1',arguments=['-Action',operation,'-Serial','phone','-AdbPath',r'C:\SDK folder\adb.exe'])]

def test_setup_not_available_on_stop(launcher):
    code,calls=launcher('Stop','Setup')
    assert code!=0 and not calls

def test_failure_propagates(launcher):
    code,calls=launcher('Start','AI',code=7)
    assert code==7 and len(calls)==1

def test_no_phone_does_not_block_pc(launcher):
    code,calls=launcher('Start','Backend',usb_code=7)
    assert code==0 and len(calls)==2

def test_cancel(launcher):
    code,calls=launcher('Start',stdin='0\n')
    assert code==0 and not calls
