"""Explicit online setup only. Application runtime never downloads models."""
from pathlib import Path
import hashlib,json,urllib.request,zipfile,shutil
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/"models/manifest.json").read_text())
for name,entry in manifest.items():
    target=root/"models"/entry["file"]
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==entry["sha256"]:
        print("Verified, reusing",target.name)
        continue
    archive=root/"models"/(name+".zip")
    if not archive.exists():
        temporary=archive.with_suffix(".download")
        with urllib.request.urlopen(entry["source"],timeout=120) as src,temporary.open("wb") as dst:
            shutil.copyfileobj(src,dst)
        temporary.replace(archive)
    with zipfile.ZipFile(archive) as z:
        member=next(x for x in z.namelist() if x.endswith("/end2end.onnx"))
        data=z.read(member)
    if hashlib.sha256(data).hexdigest()!=entry["sha256"]:
        raise RuntimeError(f"Model integrity mismatch: {archive}; existing model untouched")
    tmp=target.with_suffix(".tmp");tmp.write_bytes(data);tmp.replace(target)
    print("Verified, extracted",target.name)
