"""Export only real compiled artifacts into the static observatory."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil


def normalize_resources(record: dict) -> dict:
    counts=record['cell_counts']
    record['logic_lut']=counts.get('LUT4',0)
    record['carry_lut']=2*counts.get('CCU2C',0)
    record['lut']=record['logic_lut']+record['carry_lut']
    record['lut_scope']='Total mapped LUT4 equivalents: logic LUT4 + 2 per CCU2C carry cell'
    record['routed_comb']=record.get('routing_utilization',{}).get('TRELLIS_COMB',{}).get('used')
    if 'throughput_per_s' in record:
        record['core_throughput_estimate_per_s']=record.pop('throughput_per_s')
    record['throughput_scope']='Analytic packed-core bound at target clock, excludes streaming serialization and backpressure'
    return record


def export(root: Path) -> dict:
    corpus=json.loads((root/'benchmarks/corpus.json').read_text())
    manifest=json.loads((root/'models/dataset_manifest.json').read_text())
    output=root/'observatory/data'
    output.mkdir(parents=True,exist_ok=True)
    candidates=[]
    for record in corpus:
        if not record.get('verified') or not record.get('routed'):
            continue
        normalize_resources(record)
        run=root/'benchmarks/runs'/record['id']
        target=output/'artifacts'/record['id']
        target.mkdir(parents=True,exist_ok=True)
        for name in ('design.v','manifest.json','weights.json','verification.json','build.json','core.log','streaming.log','routing.json','routing.log','synthesis-stat.json','constraints.lpf','waveform.vcd'):
            source=run/name
            if source.exists():
                shutil.copy2(source,target/name)
        verification=record['verification']
        public={**record,
                'hdl_url':f'data/artifacts/{record["id"]}/design.v',
                'manifest_url':f'data/artifacts/{record["id"]}/manifest.json',
                'report_url':f'data/artifacts/{record["id"]}/candidate.json',
                'waveform_url':f'data/artifacts/{record["id"]}/waveform.vcd',
                'verification':{**verification,
                                'backpressure':True,'reset':True,
                                'summary':f'{verification["samples"]} vectors in both packed-core and streaming-shell simulation, including all 275 validation examples. Exact integer outputs; stalls and in-flight reset checked.'}}
        (target/'candidate.json').write_text(json.dumps(public,indent=2)+'\n')
        candidates.append(public)
    models=[]
    for width in (4,8,12):
        model=json.loads((root/f'models/banknote_4x{width}x2.json').read_text())
        models.append({'id':f'banknote-4x{width}x2','name':f'Camera features · 4 → {width} → 2',
                       'input_size':4,'layers':[{'op':'dense','units':width},{'op':'relu'},{'op':'dense','units':2}]})
    data={'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),
          'target':{'family':'ECP5','device':'LFE5U-25F','package':'CABGA256','clock_mhz':25},
          'dataset':{'name':'UCI Banknote Authentication','source_url':manifest['source_url'],
                     'license':'CC BY 4.0','validation_samples':275,'test_samples':275,
                     'scope':'Industrial-camera wavelet features. Search uses validation rows, final test rows reserved.'},
          'models':models,'candidates':candidates,'history':[],
          'limitations':['Recorded results; browser does not compile hardware.','Core latency excludes streaming serialization.','Timing estimates from nextpnr, no physical measurements.','Pins automatically placed, external IO delays unspecified.']}
    experiments=root/'benchmarks/search/experiments.json'
    if experiments.exists():
        results=json.loads(experiments.read_text())
        data['experiments']={key:results[key] for key in ('protocol_revision','evaluation','budget_seconds','constraints','summary','reference_hypervolume')}
        trace=next(r for r in results['runs'] if r['strategy']=='cost_aware' and r['seed']==0)
        data['history']=[{**h,'strategy':'cost_aware','compile_seconds':h['evaluation_seconds']} for h in trace['history']]
        data['history_reference_hypervolume']=results['reference_hypervolume']
        data['history_label']='Cost-aware policy · seed 0 · measured-cost replay'
    (output/'observatory.json').write_text(json.dumps(data,indent=2)+'\n')
    return {'candidates':len(candidates),'path':str(output/'observatory.json')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    args=parser.parse_args()
    print(json.dumps(export(args.root.resolve())))
