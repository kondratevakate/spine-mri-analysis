"""Exercise the rendered offline workstation in Edge and capture its review states."""

import base64
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
import websocket

artifact = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(exist_ok=True, parents=True)
edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
profile = tempfile.mkdtemp(prefix="panel-review-", dir=None)
process = subprocess.Popen(
    [
        str(edge),
        "--headless",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
        "--no-first-run",
        "--remote-allow-origins=*",
        "--remote-debugging-port=" + str(port),
        "--user-data-dir=" + profile,
        artifact.as_uri(),
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
seq = 0
for _ in range(100):
    try:
        tabs = requests.get(f"http://localhost:{port}/json", timeout=2).json()
        tab = next(t for t in tabs if artifact.name in t["url"])
        break
    except (requests.RequestException, StopIteration):
        time.sleep(0.25)
ws = websocket.create_connection(
    tab["webSocketDebuggerUrl"], suppress_origin=True, timeout=60
)


def send(method, **params):
    global seq
    seq += 1
    ws.send(json.dumps(dict(id=seq, method=method, params=params)))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == seq:
            assert "error" not in r, r
            return r.get("result", {})


def js(expr):
    r = send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
    assert "exceptionDetails" not in r, r.get("exceptionDetails")
    return r["result"].get("value")


def size(w, h):
    send(
        "Emulation.setDeviceMetricsOverride",
        width=w,
        height=h,
        deviceScaleFactor=1,
        mobile=False,
    )


def shot(name):
    js("Promise.all([...document.images].map(im=>im.decode().catch(()=>{})))")
    time.sleep(0.18)
    img = send("Page.captureScreenshot", format="png", captureBeyondViewport=False)
    (out / (name + ".png")).write_bytes(base64.b64decode(img["data"]))


try:
    size(1440, 960)
    for _ in range(120):
        if js("!!window.review3d?.getState().ready"):
            break
        time.sleep(0.25)
    assert js("review3d.getState().meshCount>=2"), js("document.body.innerText")
    assert js(
        "document.querySelectorAll('.tag').length===5 && review3d.landmarks.every(l=>l.uv.every(v=>v>0&&v<1))"
    )
    assert js(
        "Object.values(review3d.meshes).every(m=>m.geometry.attributes.position.count>500 && [...m.geometry.attributes.position.array].every(Number.isFinite))"
    )
    shot("spine-3d-overview")
    original = js("review3d.camera.position.toArray()")
    js("document.querySelector('#focus').click()")
    assert js("review3d.getState().zoom>2")
    shot("spine-3d-focus")
    assert js("review3d.camera.position.distanceTo(review3d.controls.target)<200")
    js(
        "document.querySelector('#opacity').value=35;document.querySelector('#opacity').dispatchEvent(new Event('input'))"
    )
    assert js("review3d.meshes.vertebrae.material.opacity===.35")
    js(
        "document.querySelector('#plane').click();document.querySelector('#side').click()"
    )
    shot("spine-3d-plane")
    js("document.querySelector('#axial').click()")
    time.sleep(0.4)
    assert js(
        "review3d.getState().mode==='axial' && document.querySelector('#contourLabel').hidden"
    )
    js(
        "document.querySelector('#next').click();document.querySelector('#zoomImage').click()"
    )
    time.sleep(0.3)
    shot("spine-3d-axial")
    js("document.querySelector('#sag').click();review3d.choose(0,true)")
    time.sleep(0.4)
    assert js(
        "review3d.getState().selected===0 && document.querySelector('#sliceTitle').textContent.includes('L1/L2')"
    )
    assert js("review3d.getState().zoom===2.3")
    js(
        "document.querySelector('#reset').click();document.querySelector('#fullImage').click()"
    )
    assert js(
        "review3d.camera.position.distanceTo(review3d.controls.target)>200 && review3d.getState().zoom===1"
    )
    size(390, 844)
    assert js("document.documentElement.scrollWidth<=391")
    print(
        "3D geometry, focus, MRI plane, reference markers, linked images and zoom checks passed",
        flush=True,
    )
finally:
    try:
        send("Browser.close")
    except Exception:
        pass
    ws.close()
