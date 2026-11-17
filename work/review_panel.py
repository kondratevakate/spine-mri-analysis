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

out = Path(sys.argv[1]).resolve()
edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
profile = tempfile.mkdtemp(prefix="panel-review-", dir=Path(__file__).parent)
process = subprocess.Popen([str(edge), "--headless", "--disable-gpu", "--no-first-run",
        "--remote-allow-origins=*", "--remote-debugging-port="+str(port), "--user-data-dir="+profile,
        (out/"spine-review.html").as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
seq = 0
for _ in range(100):
    try:
        tabs = requests.get(f"http://localhost:{port}/json",timeout=2).json()
        tab = next(t for t in tabs if "spine-review.html" in t["url"])
        break
    except (requests.RequestException, StopIteration):
        time.sleep(.25)
ws = websocket.create_connection(tab["webSocketDebuggerUrl"], suppress_origin=True, timeout=20)
def send(method, **params):
    global seq
    seq += 1
    ws.send(json.dumps(dict(id=seq,method=method,params=params)))
    while True:
        r=json.loads(ws.recv())
        if r.get("id")==seq:
            assert "error" not in r, r
            return r.get("result", {})
def js(expr):
    r=send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
    assert "exceptionDetails" not in r, r.get("exceptionDetails")
    return r["result"].get("value")
def size(w,h):
    send("Emulation.setDeviceMetricsOverride",width=w,height=h,deviceScaleFactor=1,mobile=False)
def shot(name):
    js("Promise.all([...document.images].map(im=>im.decode().catch(()=>{})))")
    time.sleep(.18)
    img=send("Page.captureScreenshot",format="png",captureBeyondViewport=False)
    (out/(name+".png")).write_bytes(base64.b64decode(img["data"]))
def slider(key,value):
    js(f"$('{key}').value={value};$('{key}').dispatchEvent(new Event('input',{{bubbles:true}}))")
def click(selector):
    js(f"document.querySelector({json.dumps(selector)}).click()")
def stats():
    return js("Object.fromEntries(['studyid','vlevel','decision','ref','outcome','detected','falsepos','accuracy','deferred'].map(k=>[k,$(k).textContent]))")

try:
    for _ in range(100):
        if js("document.querySelector('#population')?.textContent?.length>0"):break
        time.sleep(.15)
    size(1440,900)
    assert js("D.q.length===308 && D.bank.length===299 && new Set([...D.q,...D.bank].map(x=>x.id)).size===607")
    assert js("document.querySelectorAll('.match').length===10 && $('vlevel').textContent==='L4/L5'")
    assert js("document.querySelector('.match img').naturalWidth===128")
    assert js("[...document.images].every(im=>im.complete&&im.naturalWidth>0)")
    initial=stats()
    assert initial["decision"]=="Moderate" and initial["outcome"]=="Error", initial
    print("Initial", initial, flush=True)
    shot("spine-review-initial")
    slider("threshold",35)
    changed=stats()
    assert changed["decision"]=="Severe" and changed["outcome"]=="Correct" and initial["detected"]!=changed["detected"],changed
    print("Adjusted", changed, flush=True)
    shot("spine-review-threshold")
    click("#filters button:nth-child(3)")
    assert js("[...document.querySelectorAll('.match .status')].every(e=>e.textContent==='Error') && document.querySelectorAll('.match').length>0")
    shot("spine-review-errors")
    click(".match")
    assert js("$('compare').open && $('pair').querySelectorAll('img').length===2")
    shot("spine-review-compare")
    click("#close")
    click("#reset")
    slider("conf",95)
    assert stats()["decision"]=="Deferred" and js("!!$('overlay').querySelector('[stroke-dasharray]')")
    click("#filters button:nth-child(4)")
    assert js("[...document.querySelectorAll('.match .status')].every(e=>e.textContent==='Deferred')")
    click("#show")
    assert js("$('overlay').childElementCount===0")
    click("#show");click("#reset")
    for i in [0,1,3,4]:slider("w"+str(i),0)
    assert js("assess(D.q[state.q],state.l).p.every((p,k)=>Math.abs(p-D.q[state.q].p[state.l][2][k])<1e-9)")
    slider("w2",0)
    assert stats()["decision"]=="Weights off" and stats()["detected"]=="—"
    click("#reset")
    js("$('rule').value='top';$('rule').dispatchEvent(new Event('input'))")
    assert js("$('threshold').disabled")
    click("#levels button:first-child");click("#next")
    assert stats()["vlevel"]=="L1/L2" and stats()["studyid"]!=initial["studyid"]
    assert js("document.querySelectorAll('.col:nth-child(2) .match').length===Math.min(5,D.bank.filter(r=>r.grade[0]===2).length)")
    slider("conf",100)
    click("#filters button:nth-child(2)")
    assert js("document.querySelectorAll('.empty').length===2")
    js("let g=document.querySelector('.colselect');g.value=2;g.dispatchEvent(new Event('change'));")
    assert js("state.group.join(',')==='2,1'")
    size(390,844)
    assert js("document.documentElement.scrollWidth<=391"), js("document.documentElement.scrollWidth")
    print("Interaction checks passed",flush=True)
finally:
    try: send("Browser.close")
    except Exception: pass
    ws.close()
