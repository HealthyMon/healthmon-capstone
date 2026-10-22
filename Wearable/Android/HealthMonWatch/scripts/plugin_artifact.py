"""Export or verify the plugin's source/AAR identity after a successful Gradle build.

Usage: python scripts/plugin_artifact.py export
       python scripts/plugin_artifact.py verify --unity ../../../Client/HealthMonUnity/Assets/Plugins/Android/healthmon-mobile-plugin-release.aar
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[2]
MODULE = PROJECT / "healthmon-mobile-plugin"
ARTIFACT = PROJECT.parent / "Artifacts/healthmon-mobile-plugin-release.aar"
PROVENANCE = ARTIFACT.with_suffix(".provenance.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources() -> dict[str, str]:
    paths = list((MODULE / "src/main").rglob("*"))
    paths += list((MODULE / "schemas").rglob("*.json"))
    paths += [MODULE / "build.gradle.kts", PROJECT / "build.gradle.kts",
              PROJECT / "settings.gradle.kts", PROJECT / "gradle/libs.versions.toml",
              PROJECT / "gradle/wrapper/gradle-wrapper.properties"]
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(paths) if p.is_file()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["export", "verify"])
    parser.add_argument("--unity", type=Path)
    args = parser.parse_args()
    if args.command == "export":
        built = MODULE / "build/outputs/aar/healthmon-mobile-plugin-release.aar"
        if not built.is_file():
            parser.error("Build the release AAR and run its tests with Gradle before exporting.")
        shutil.copyfile(built, ARTIFACT)
        data = {"format_version": 1,
                "build_command": "gradlew :healthmon-mobile-plugin:testDebugUnitTest :healthmon-mobile-plugin:assembleRelease",
                "artifact": ARTIFACT.relative_to(ROOT).as_posix(),
                "artifact_sha256": sha256(ARTIFACT), "sources": sources()}
        PROVENANCE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    data = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    if data["artifact_sha256"] != sha256(ARTIFACT):
        parser.error("AAR does not match its recorded build provenance.")
    if data["sources"] != sources():
        parser.error("Plugin source changed after AAR export; rebuild and test before exporting.")
    if args.unity and sha256(args.unity) != data["artifact_sha256"]:
        parser.error("Unity contains a different AAR; preserve its .meta and copy the verified artifact.")
    print(f"Verified {len(data['sources'])} source files and AAR {data['artifact_sha256']}")


if __name__ == "__main__":
    main()
