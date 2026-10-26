"""Freeze real corpus measurements and current genuine app screenshots into film assets."""
from pathlib import Path
import hashlib
import html
import json
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ASSETS=HERE/'composition/assets'
ASSETS.mkdir(parents=True,exist_ok=True)
records=json.loads((ROOT/'benchmarks/corpus.json').read_text())
main=[r for r in records if r['model_width']==8]
compact=next(r for r in main if r['id']=='w8-c16')
accurate=next(r for r in main if r['id']=='w8-c22')
source_files=[ROOT/'benchmarks/corpus.json', ROOT/'observatory/index.html', ROOT/'observatory/style.css', ROOT/'observatory/app.js', ROOT/'observatory/data/observatory.json', ROOT/'benchmarks/runs/w8-c16/design.v']
capture_count=0
for name in ('pareto.png','constrained-pareto.png','verification.png','waveform.png','hdl.png'):
    source=ROOT/'docs/media'/name
    if source.exists():
        shutil.copyfile(source,ASSETS/name)
        source_files.append(source)
        capture_count+=1
# Keep a versioned data snapshot: charts never use invented point coordinates.
(ASSETS/'measurements.json').write_text(json.dumps(records,indent=2)+'\n')
xs=[float(r['latency_us']) for r in main];ys=[float(r['accuracy'])*100 for r in main]
xmin,xmax=0,max(xs)*1.08
ymin,ymax=float(int(min(ys))-1),100.0
points=[]
for r,x,y in zip(main,xs,ys):
    sx=95+(x-xmin)/(xmax-xmin)*1000
    sy=415-(y-ymin)/(ymax-ymin)*320
    points.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="7" fill="#d94a25" opacity=".8"><title>{r["id"]}: {x}us, {y}%</title></circle>')
lines=[]
for k in range(5):
    y=95+k*80
    val=ymax-k*(ymax-ymin)/4
    lines.append(f'<path d="M95 {y}H1095" stroke="#d9dcd3" stroke-dasharray="3 7"/><text x="70" y="{y+7}" text-anchor="end">{val:.1f}%</text>')
for k in range(5):
    x=95+k*250
    val=xmin+k*(xmax-xmin)/4
    lines.append(f'<text x="{x}" y="458" text-anchor="middle">{val:.1f}</text>')
chart=f'<svg viewBox="0 0 1160 520" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Real measured latency and accuracy tradeoffs"><style>text{{font:20px Menlo,monospace;fill:#626d64}}</style>{"".join(lines)}{"".join(points)}<text x="95" y="45">4 → 8 → 2 / VALIDATION ACCURACY</text><text x="1095" y="507" text-anchor="end">CORE LATENCY / µs AT 25MHz</text></svg>'
(ASSETS/'measured-frontier.svg').write_text(chart)

def card(r):
    c=r['config']
    return f'<span class="mono">{r["id"]} / {c["bits"]}-BIT · {c["parallelism"]} LANE</span><div class="card-number">{r["latency_us"]:.2f}<small>µs core latency</small></div><div class="card-row"><span>{r["lut"]:,} LUT4</span><span>{r["accuracy"]*100:.0f}% accuracy</span></div>'
replacements={'@@COUNT@@':str(len(records)),'@@COMPACT@@':card(compact),'@@ACCURATE@@':card(accurate),'@@SAMPLES@@':str(accurate['verification']['samples']),'@@DATASET@@':str(accurate['verification']['dataset_samples'])}
template=(HERE/'template.html').read_text()
for token,value in replacements.items(): template=template.replace(token,value)
(HERE/'composition/index.html').write_text(template)
provenance={'scope':'authentic current local app captures and measured-corpus snapshot','corpus_records':len(records),'comparison_ids':[compact['id'],accurate['id']],'files':[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in source_files],'gsap':{'version':'3.14.2','license':'https://gsap.com/standard-license','usage':'free local animation runtime; original header retained'}}
(HERE/'source-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(f'Built 60s composition from {len(records)} measured records and {capture_count} UI captures.')
