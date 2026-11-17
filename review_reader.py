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
        "--disable-gpu",
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
    tab["webSocketDebuggerUrl"], suppress_origin=True, timeout=20
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
    for _ in range(120):
        if js("document.querySelector('#rows')?.children.length===5"):
            break
        time.sleep(0.25)
    size(1440, 900)
    assert js(
        "D.q.length===308 && D.bankSize===299 && document.querySelectorAll('.mark').length===5"
    )
    assert js(
        "D.q.every(r=>r.neighbors.every((lv,l)=>lv.every((ids,g)=>ids.length<=5 && new Set(ids).size===ids.length && ids.every(i=>D.bank[i].id!==r.id && D.bank[i].call[l]===g && D.bank[i].ref[l]===g && (r.ax[l].images.length===1 || D.bank[i].ax[l].images.length===3)))))"
    )
    assert js("$('blind').checked && $('refs').hidden && $('assist').hidden")
    shot("reader-blind")
    js("$('reveal').click()")
    assert js(
        "document.querySelector('.refitem')!==null && !document.querySelector('#assist details')"
    )
    print("Opening columns:", js("current().neighbors[3].map(g=>g.length)"), flush=True)
    shot("reader-overview")
    js("document.querySelector('.refitem').click()")
    assert js("$('dialog').open && $('pairs').querySelectorAll('img').length===4")
    js("$('dnext').click()")
    assert js("$('dpos').textContent==='Superior'")
    shot("reader-comparison")
    js("$('close').click();$('blind').click()")
    assert js(
        "$('refs').hidden && $('assist').hidden && !$('rows').innerText.includes('Model')"
    )
    js("$('choices').lastElementChild.click();selectLevel(1);selectLevel(3)")
    assert js("entry(3)==='Insufficient images' && entry(1)===''")
    js(
        "$('blind').click();$('choices').children[1].click();$('mode').value='around';draw()"
    )
    assert js(
        "groups(current()).join(',')==='0,2' && worksheet().includes('First: Insufficient images (after assistance was shown) | Final: Moderate')"
    )
    js("$('choices').children[2].click()")
    assert js(
        "document.querySelector('.groups').textContent.includes('Scale endpoint')"
    )
    js("location.reload()")
    for _ in range(80):
        if js(
            "document.querySelector('#readerstatus')?.textContent?.includes('Recorded')"
        ):
            break
        time.sleep(0.2)
    assert js("entry(3)==='Severe'")
    js(
        "study=D.q.findIndex(r=>r.id==='953639220');selectLevel(2);$('choices').children[1].click();$('reveal').click()"
    )
    assert js(
        "worksheet().includes('First: Moderate (before assistance)') && !$('rows').children[0].innerText.includes('Model')"
    )
    assert js(
        "current().neighbors[2][2].length===0 && !!document.querySelector('.empty')"
    )
    assert js("current().neighbors[2][1].length>0")
    js("document.querySelector('.refitem').click()")
    assert js(
        "$('dprev').disabled && $('dnext').disabled && $('dpos').textContent.includes('Single')"
    )
    js("$('close').click()")
    print(
        "Independent case column counts:",
        js("current().neighbors[2].map(g=>g.length)"),
        flush=True,
    )
    size(1280, 720)
    assert js(
        "document.querySelectorAll('.row')[4].getBoundingClientRect().bottom<=720"
    )
    shot("reader-l3-review")
    size(390, 844)
    assert js("document.documentElement.scrollWidth<=391")
    print(
        "Reader, stored answers, grade endpoints, eligible bank, viewport and worksheet checks passed."
    )
finally:
    try:
        send("Browser.close")
    except Exception:
        pass
    ws.close()
