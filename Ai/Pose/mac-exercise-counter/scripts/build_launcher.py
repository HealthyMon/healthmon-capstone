"""Native macOS bundle hosting the existing project Python virtual environment."""
from pathlib import Path
import plistlib,sysconfig,subprocess,json
root=Path(__file__).resolve().parents[1]
bundle=root/"Local Motion.app"
macos=bundle/"Contents/MacOS"; macos.mkdir(parents=True,exist_ok=True)
python=str(root/".venv/bin/python")
src=root/"scripts/launcher.c"
src.write_text('''#include <Python.h>
#include <stdlib.h>
#include <unistd.h>
int main(int argc, char **argv) {
    setenv("PYTHONPATH", PROJECT_SOURCE, 1);
    chdir(PROJECT_ROOT);
    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    PyStatus status = PyConfig_SetBytesString(&config, &config.program_name, PYTHON_PATH);
    if (PyStatus_Exception(status)) Py_ExitStatusException(status);
    status = PyConfig_SetBytesArgv(&config, argc, argv);
    if (PyStatus_Exception(status)) Py_ExitStatusException(status);
    if (argc == 1) {
        status = PyConfig_SetString(&config, &config.run_module, L"exercise_counter.app");
        if (PyStatus_Exception(status)) Py_ExitStatusException(status);
    }
    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) Py_ExitStatusException(status);
    return Py_RunMain();
}
''')
lib=Path(sysconfig.get_config_var("LIBDIR"))
subprocess.run(["cc",str(src),"-I"+sysconfig.get_path("include"),"-L"+str(lib),"-lpython3.12",
    "-Wl,-rpath,"+str(lib),'-DPYTHON_PATH='+json.dumps(python),
    '-DPROJECT_SOURCE='+json.dumps(str(root/"src")),'-DPROJECT_ROOT='+json.dumps(str(root)),
    "-o",str(macos/"LocalMotion")],check=True)
info={"CFBundleName":"Local Motion","CFBundleDisplayName":"Local Motion","CFBundleIdentifier":"local.exercise.counter",
      "CFBundleExecutable":"LocalMotion","CFBundleVersion":"1","CFBundleShortVersionString":"0.1.0",
      "CFBundlePackageType":"APPL","LSMinimumSystemVersion":"13.0","NSHighResolutionCapable":True,
      "NSCameraUsageDescription":"카메라 영상을 이 Mac에서만 분석하여 운동 횟수를 셉니다. 영상은 저장하거나 전송하지 않습니다."}
(bundle/"Contents/Info.plist").write_bytes(plistlib.dumps(info))
subprocess.run(["codesign","--force","--sign","-",str(bundle)],check=True)
print(bundle)
