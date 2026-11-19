#include <Python.h>
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
