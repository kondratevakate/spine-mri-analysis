"""Fetch pinned Three.js browser assets for the fully offline viewer build."""

import hashlib
import json
from pathlib import Path

import requests

ASSETS = {
    "three.module.js": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js",
    "OrbitControls.js": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js",
    "THREE-LICENSE.txt": "https://cdn.jsdelivr.net/npm/three@0.160.0/LICENSE",
}


if __name__ == "__main__":
    folder = Path("work/vendor")
    folder.mkdir(exist_ok=True, parents=True)
    manifest = {}
    for name, url in ASSETS.items():
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        (folder / name).write_bytes(response.content)
        manifest[name] = dict(
            url=url, sha256=hashlib.sha256(response.content).hexdigest()
        )
    (folder / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf8"
    )
    print("Three.js 0.160.0 assets and license saved.")
