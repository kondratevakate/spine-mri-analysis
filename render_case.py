"""Render one study through the pipeline: input -> levels -> grades -> culprit -> draft report.

Uses saved outputs only (no new inference): images and reference crops from relocalize.py,
automatic crops and landmarks from the cached sagittal features, and test predictions of arm A
(deployed path: automatic localizer + original weights) and arm C (radiologist landmarks).

Usage: python render_case.py DATA RELOCALIZED_DIR STUDY_ID OUTPUT_HTML
"""

import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

LEVELS = ["L1/L2", "L2/L3", "L3/L4", "L4/L5", "L5/S1"]
GRADES = ["Normal/mild", "Moderate", "Severe"]


def png(array, size=None):
    im = Image.fromarray(array) if isinstance(array, np.ndarray) else array
    if size:
        im = im.resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def arm(tests, letter, study, seed_file):
    t = pd.read_csv(seed_file, dtype={"study_id": str})
    a = t[(t.arm.str[0] == letter) & (t.study_id == study)].sort_values("level")
    assert len(a) == 5, (letter, len(a))
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("relocalized", type=Path)
    ap.add_argument("study")
    ap.add_argument("out", type=Path)
    a = ap.parse_args()
    sag = np.load(a.data / "paired-features-v1" / "sagittal.npz")
    i = int(np.flatnonzero(sag["ids"] == a.study)[0])
    image = np.load(a.relocalized / "images224.npy")[i]
    ref_crops = np.load(a.relocalized / "reference-crops.npz")["crops"][i]
    auto_crops = sag["crops"][i]
    field = sag["fields"][i]
    seed_file = a.relocalized / "relocalized-test-20261116.csv"
    metrics = json.loads((a.relocalized / "relocalized-metrics-20261116.json").read_text())
    cut = {m["arm"][0]: m["threshold"] for m in metrics if "threshold" in m}
    A = arm(None, "A", a.study, seed_file)
    C = arm(None, "C", a.study, seed_file)

    big = Image.fromarray(image).convert("RGB").resize((448, 448), Image.LANCZOS)
    g = ImageDraw.Draw(big)
    for j in range(5):
        for centre, colour, width in ((sag["predicted"][i, j], "#ffd23f", 2), (sag["targets"][i, j], "#3fe0d0", 2)):
            cx, cy = centre * 448
            hx, hy = 48 / field * 448 / 2
            g.rectangle((cx - hx, cy - hy, cx + hx, cy + hy), outline=colour, width=width)
        cx, cy = sag["targets"][i, j] * 448
        g.text((cx + 52, cy - 6), LEVELS[j], fill="#3fe0d0")
    shift = np.linalg.norm((sag["predicted"][i] - sag["targets"][i]) * field, axis=1)

    def grade_row(rows, letter):
        out = []
        for j, r in enumerate(rows.itertuples()):
            alert = r.p_severe >= cut[letter]
            call = 2 if alert else int(np.argmax([r.p_normal_mild, r.p_moderate]))
            out.append(dict(call=call, ps=r.p_severe, ref=int(r.grade), alert=bool(alert)))
        return out

    ga, gc = grade_row(A, "A"), grade_row(C, "C")
    cls = {0: "g0", 1: "g1", 2: "g2"}
    level_rows = ""
    for j in range(5):
        x, y = ga[j], gc[j]
        level_rows += (
            f"<tr><td class=lv>{LEVELS[j]}</td>"
            f"<td><img src='{png(auto_crops[j], (110, 110))}'><div class=sm>{shift[j]:.0f} mm off</div></td>"
            f"<td><span class='pill {cls[x['call']]}'>{GRADES[x['call']]}</span><div class=bar><i style='width:{100 * x['ps']:.0f}%'></i></div><div class=sm>P(severe) {x['ps']:.2f}</div></td>"
            f"<td><img src='{png(ref_crops[j], (110, 110))}'></td>"
            f"<td><span class='pill {cls[y['call']]}'>{GRADES[y['call']]}</span><div class=bar><i style='width:{100 * y['ps']:.0f}%'></i></div><div class=sm>P(severe) {y['ps']:.2f}</div></td>"
            f"<td><span class='pill {cls[x['ref']]}'>{GRADES[x['ref']]}</span></td></tr>"
        )
    culprit_a = int(np.argmax([r["ps"] for r in ga]))
    culprit_c = int(np.argmax([r["ps"] for r in gc]))

    def report(rows, culprit):
        sev = [LEVELS[j] for j, r in enumerate(rows) if r["call"] == 2]
        mod = [LEVELS[j] for j, r in enumerate(rows) if r["call"] == 1]
        f = []
        for j, r in enumerate(rows):
            f.append(f"{LEVELS[j]}: {GRADES[r['call']].lower()} central canal stenosis.")
        imp = []
        if sev:
            imp.append(f"Severe central canal stenosis at {', '.join(sev)}; most pronounced at {LEVELS[culprit]}.")
        if mod:
            imp.append(f"Moderate central canal stenosis at {', '.join(mod)}.")
        if not imp:
            imp.append("No moderate or severe central canal stenosis.")
        imp.append("Cause: [not assessed]. Correlate with symptoms and examination.")
        return "<br>".join(f), "<br>".join(imp)

    fa, ia = report(ga, culprit_a)
    fc, ic = report(gc, culprit_c)
    html = f"""<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Case Walkthrough</title><style>
:root{{--bg:#0f161d;--card:#18222c;--ink:#e8eef3;--mute:#9fb0bf;--line:#2c3a47;--y:#ffd23f;--c:#3fe0d0}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.4 "Segoe UI",system-ui,sans-serif}}
main{{max-width:1500px;margin:auto;padding:20px 16px}}h1{{font-size:22px;margin:0 0 4px}}.sub{{color:var(--mute);margin:0 0 14px}}
.grid{{display:grid;grid-template-columns:470px 1fr;gap:14px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}}
h2{{font-size:13px;letter-spacing:.05em;text-transform:uppercase;color:var(--mute);margin:0 0 8px}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:4px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:middle}}th{{font-size:12px;color:var(--mute);font-weight:600}}
td img{{display:block;width:110px;height:110px;border-radius:4px}}.lv{{font-weight:700;font-size:16px}}.sm{{font-size:11.5px;color:var(--mute)}}
.pill{{display:inline-block;padding:2px 8px;border-radius:10px;font-weight:700;font-size:12.5px}}.g0{{background:#21423a;color:#8ff0c8}}.g1{{background:#4a3b17;color:#ffd98a}}.g2{{background:#5a2020;color:#ffb3b3}}
.bar{{height:6px;background:var(--line);border-radius:3px;margin:5px 0 2px;width:120px}}.bar i{{display:block;height:100%;background:#fc8181;border-radius:3px}}
.rep{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}.rep p{{margin:4px 0;font-family:Consolas,monospace;font-size:13px}}
.key{{font-size:12.5px;color:var(--mute)}}.y{{color:var(--y)}}.c{{color:var(--c)}}
@media(max-width:1000px){{.grid,.rep{{grid-template-columns:1fr}}td img{{width:70px;height:70px}}}}
</style><main>
<h1>Study {a.study}: from MRI to a draft report</h1>
<p class=sub>Internal RSNA test case, central canal only. Model output for research; a radiologist must review every line.</p>
<div class=grid>
<div class=card><h2>1 · Levels on sagittal T2</h2><img src="{png(big)}" style="width:100%;border-radius:4px">
<p class=key><b class=y>Yellow</b> automatic localizer (what the system uses) · <b class=c>cyan</b> radiologist landmark (RSNA). Crop width 48 mm.</p></div>
<div class=card><h2>2 · Grade per level</h2><table>
<tr><th>Level</th><th class=y>Automatic crop</th><th>System grade</th><th class=c>Landmark crop</th><th>Grade with landmarks</th><th>RSNA reference</th></tr>
{level_rows}</table>
<p class=key>Severe is called when P(severe) passes the validation-frozen threshold (automatic {cut["A"]:.2f}, landmark {cut["C"]:.2f}).</p></div>
</div>
<div class=rep>
<div class=card><h2>3–5 · Draft report, system as deployed (automatic levels)</h2><p><b>Findings</b><br>{fa}</p><p><b>Impression</b><br>{ia}</p></div>
<div class=card><h2>3–5 · Draft report with radiologist landmarks</h2><p><b>Findings</b><br>{fc}</p><p><b>Impression</b><br>{ic}</p></div>
</div>
<p class=key style="margin-top:12px">Step 4 (cause) and step 6 (similar patients by cause and outcome) are not built: RSNA has no cause or outcome labels.</p>
</main></html>"""
    a.out.write_text(html, encoding="utf8")
    print("saved", a.out, "culprit automatic", LEVELS[culprit_a], "landmark", LEVELS[culprit_c])


if __name__ == "__main__":
    main()
