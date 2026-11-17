"""Render the executed compiler/RTL comparison; no hardware study is performed."""
from pathlib import Path
import json,hashlib,textwrap,csv
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
P=Path(__file__).resolve().parent
r=json.loads((P/'execution.json').read_text())
ink='#202927';paper='#fbfaf6';orange='#ac3b1e';green='#286b50';muted='#525e57';line='#d0d6cc'
rows=[]
for name in ['direct','overlapped']:
 m=r['cases'][name]['manifest'];v=r['cases'][name]['verification'];s=m['stage_compute_cycles'];assert sum(s)+1==v['latency_cycles'];assert v['results']['schedule']['latency_cycles']==v['latency_cycles'];assert v['samples']==78
 rows.append({'schedule':name,'stage0':s[0],'handoff':1,'stage1':s[1],'latency':v['latency_cycles'],'interval':v['initiation_interval_cycles']})
with (P/'schedule.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator="\n");w.writeheader();w.writerows(rows)
outputs=[]
with mpl.rc_context({'font.family':['DejaVu Sans','Arial','sans-serif'],'svg.fonttype':'none','svg.hashsalt':'siliconpilot-presentation-v1','figure.facecolor':paper,'axes.facecolor':paper,'text.color':ink,'axes.labelcolor':muted,'xtick.color':muted,'path.simplify':False}):
 for mobile in [False,True]:
  fig=plt.figure(figsize=(6,9.6) if mobile else (12,7.4));fig.patch.set_facecolor(paper)
  left=.085 if mobile else .06
  fig.text(left,.947,'SILICONPILOT / EXECUTED RTL',fontsize=10 if mobile else 11,color=green,weight='bold')
  fig.text(left,.90 if mobile else .91,'One classifier.\nTwo clocked circuits.',fontsize=27 if mobile else 32,weight='bold',linespacing=1.08,va='top')
  fig.text(left,.775 if mobile else .765,'4 → 8 → 2 dense / ReLU · signed W8 / F5 / A24',fontsize=12,color=muted)
  fig.text(left,.735 if mobile else .718,'Same quantized weights. Same 78 checked vectors.',fontsize=12 if mobile else 14)
  ax=fig.add_axes([left,.365 if mobile else .30,.84 if mobile else .82,.285 if mobile else .32])
  ax.set_xlim(0,54);ax.set_ylim(-.52,1.72);ax.set_yticks([]);ax.set_xticks([0,10,20,30,40,50]);ax.set_xlabel('Core clocks from input acceptance',fontsize=11,labelpad=9)
  ax.spines[['left','right','top']].set_visible(False);ax.spines['bottom'].set_color(line);ax.grid(axis='x',color=line,linewidth=.7,zorder=0)
  for row,y in zip(rows,[1.12,.02]):
   label='1 lane · direct products' if row['schedule']=='direct' else '2 lanes · registered products'
   ax.text(0,y+.27,label,fontsize=12 if mobile else 14,weight='bold')
   x=0
   for part,color,gid in [('stage0',orange,'dense-4-to-8'),('handoff','#85918b','handoff'),('stage1',green,'dense-8-to-2')]:
    rect=Rectangle((x,y-.09),row[part],.24,facecolor=color,zorder=3,gid=row['schedule']+'-'+gid);ax.add_patch(rect)
    if part!='handoff':ax.text(x+row[part]/2,y+.025,str(row[part]),ha='center',va='center',fontsize=12,color='white',weight='bold')
    x+=row[part]
   ax.text(x+.75,y+.025,str(row['latency']),fontsize=13,va='center',weight='bold')
   ax.text(0,y-.29,f"First output {row['latency']} clocks · sustained interval {row['interval']} clocks",fontsize=10.5 if mobile else 12,color=muted)
  fig.text(left,.275 if mobile else .205,'DENSE 4 → 8     /     HANDOFF     /     DENSE 8 → 2',fontsize=9.3 if mobile else 11,color=muted)
  fig.text(left,.228 if mobile else .15,'78/78 core + serial checks pass for each circuit.',fontsize=11 if mobile else 13,weight='bold',color=green)
  foot='Stage widths are manifest clock accounting; endpoint latency and output intervals were checked in RTL simulation. Both are current compiler choices, not before/after versions. No board, power or physical timing claim.'
  fig.text(left,.08 if mobile else .04,textwrap.fill(foot,62 if mobile else 136),fontsize=9 if mobile else 10,color=muted,linespacing=1.5)
  fig.canvas.draw();renderer=fig.canvas.get_renderer();fw,fh=fig.canvas.get_width_height()
  for text in fig.findobj(mpl.text.Text):
   if text.get_visible() and text.get_text():
    box=text.get_window_extent(renderer);assert box.x0>=-1 and box.y0>=-1 and box.x1<=fw+1 and box.y1<=fh+1,(text.get_text(),box,fw,fh)
  stem='schedule-mobile' if mobile else 'schedule'
  for ext in ['svg','png']:
   dest=P/f'{stem}.{ext}';fig.savefig(dest,dpi=144 if not mobile else 100,facecolor=paper,transparent=False,metadata={'Creator':'SiliconPilot presentation'} if ext=='svg' else {})
   if ext=='svg':dest.write_text('\n'.join(line.rstrip() for line in dest.read_text().splitlines())+'\n')
   outputs.append(dest)
  plt.close(fig)
manifest={'source':'execution.json','sourceSHA256':hashlib.sha256((P/'execution.json').read_bytes()).hexdigest(),'generator':'figure.py','generatorSHA256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'matplotlib':mpl.__version__,'data':rows,'encoding':'Zero-based common linear clock scale. Stage rectangles show manifest accounting; simulation independently checks first-output latency and sustained interval. No smoothing, aggregation, normalization or uncertainty interval.','fonts':['DejaVu Sans','Arial','sans-serif'],'outputs':[{'path':f.name,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in outputs]}
(P/'figure-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(rows,indent=2))
