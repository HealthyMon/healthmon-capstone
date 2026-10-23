"""Compile/run production DTO/version-gate checks; optionally compile all Unity sources.

No dependency download, scene mutation, package import or Unity license is required.
--unity-editor is the Unity Editor directory (contains Unity.exe and Data/).
--package-assemblies points to this project's existing Library/ScriptAssemblies or a
verified matching Unity/package version cache. This fallback is not an editor/build test.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


def run(command: list[str], log: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, capture_output=True, encoding="utf-8-sig", errors="replace", env=env)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    for line in result.stdout.splitlines():
        if "error " in line or "PASS" in line:
            print(line.encode("ascii", "backslashreplace").decode())
    if result.returncode:
        raise SystemExit(f"Command failed ({result.returncode}); see {log}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unity-editor", default=os.environ.get("UNITY_EDITOR_PATH"), required=not os.environ.get("UNITY_EDITOR_PATH"))
    parser.add_argument("--package-assemblies", type=Path)
    args = parser.parse_args()
    editor = Path(args.unity_editor).resolve()
    project = Path(__file__).resolve().parents[1]
    output = project / "Temp" / "CommonServerVerification"
    output.mkdir(parents=True, exist_ok=True)
    mono = editor / ("Data/MonoBleedingEdge/bin/mono.exe" if os.name == "nt" else "Data/MonoBleedingEdge/bin/mono")
    csc = editor / "Data/MonoBleedingEdge/lib/mono/4.5/csc.exe"
    scripts = project / "Assets/HealthMon/Scripts"
    exe = output / "ContractChecks.exe"
    run([str(mono), str(csc), "-nologo", "-langversion:9.0", "-out:" + str(exe),
         str(scripts / "API/CommonServerContracts.cs"), str(scripts / "API/HealthmonDtos.cs"),
         str(project / "Tests/ContractChecks.cs")], output / "contracts-compile.log")
    run([str(mono), str(exe)], output / "contracts-results.log")
    if args.package_assemblies:
        managed = editor / "Data/Managed"
        references = list((managed / "UnityEngine").glob("*.dll")) + list((managed / "UnityEditor").glob("*.dll"))
        references += [file for file in args.package_assemblies.resolve().glob("*.dll")
                       if not file.name.startswith("Assembly-CSharp")]
        references += [editor / "Data/MonoBleedingEdge/lib/mono/4.5/Facades/netstandard.dll"]
        for target, defines in [("Editor", "UNITY_EDITOR;UNITY_STANDALONE_WIN"), ("Android", "UNITY_ANDROID")]:
            sources = [file for file in scripts.rglob("*.cs") if target == "Editor" or "Editor" not in file.parts]
            options = ["-nologo", "-langversion:9.0", "-target:library", "-define:" + defines,
                       "-out:" + str(output / ("HealthMon." + target + ".dll"))]
            options += ["-r:" + str(file) for file in references]
            options += [str(file) for file in sources]
            response = output / (target + ".rsp")
            response.write_text("\n".join('"' + value + '"' for value in options), encoding="utf-8")
            run([str(mono), str(csc), "@" + str(response)], output / (target + "-compile.log"))
            print(f"HEALTHMON_{target.upper()}_CSHARP_COMPILE_PASS sources={len(sources)}")
        guard = output / "AuthorityGuardChecks.exe"
        options = [str(mono), str(csc), "-nologo", "-out:" + str(guard),
                   "-r:" + str(output / "HealthMon.Android.dll")]
        options += ["-r:" + str(file) for file in references]
        options += [str(project / "Tests/AuthorityGuardChecks.cs")]
        run(options, output / "authority-compile.log")
        guard_env = os.environ.copy()
        guard_env["MONO_PATH"] = os.pathsep.join([str(output), str(managed / "UnityEngine"),
                                                  str(args.package_assemblies.resolve())])
        run([str(mono), str(guard)], output / "authority-results.log", env=guard_env)
        outcome = output / "NativeOutcomeChecks.exe"
        options = [str(mono), str(csc), "-nologo", "-out:" + str(outcome),
                   "-r:" + str(output / "HealthMon.Editor.dll")]
        options += ["-r:" + str(file) for file in references]
        options += [str(project / "Tests/NativeOutcomeChecks.cs")]
        run(options, output / "native-outcome-compile.log")
        run([str(mono), str(outcome)], output / "native-outcome-results.log", env=guard_env)
    print("Verification output:", output)


if __name__ == "__main__":
    main()
