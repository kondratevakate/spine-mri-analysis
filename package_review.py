"""Create a local, checksummed reviewer package from a committed source tree."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def main(out):
    if git("status", "--porcelain"):
        raise ValueError("Commit the reviewed source before packaging")
    source = out / "spine-mri-analysis.bundle"
    git("bundle", "create", str(source), "--all")
    git("bundle", "verify", str(source))
    files = {
        "README.md": Path("README.md"),
        "REVIEW.md": Path("REVIEW.md"),
        "STATE.md": Path("STATE.md"),
        "source.bundle": source,
        "spine-review.html": out / "spine-review.html",
        "spine-reader-v2.html": out / "spine-reader-v2.html",
        "spine-3d.html": out / "spine-3d.html",
        "marker-audit.json": out / "marker-audit.json",
    }
    for name in [
        "reader-overview",
        "reader-blind",
        "reader-comparison",
        "reader-l3-review",
        "spine-3d-overview",
        "spine-3d-focus",
        "spine-3d-plane",
        "spine-3d-axial",
        "marker-audit",
        "segmentation-qc",
    ]:
        files[f"screenshots/{name}.png"] = out / f"{name}.png"
    archive = out / "lumbar-mri-review-v3.zip"
    manifest = {"commit": git("rev-parse", "HEAD"), "sha256": {}}
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=3) as zipfile:
        for name, path in files.items():
            with path.open("rb") as stream:
                manifest["sha256"][name] = digest(stream)
            zipfile.write(path, name)
        zipfile.writestr("manifest.json", json.dumps(manifest, indent=2))
    with ZipFile(archive) as zipfile:
        for name, expected in manifest["sha256"].items():
            with zipfile.open(name) as stream:
                assert digest(stream) == expected, name
    print(archive, archive.stat().st_size, manifest["commit"])


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
