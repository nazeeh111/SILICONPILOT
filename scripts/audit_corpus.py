"""Read back evidence, normalize resource definitions, refresh protocol tests."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from siliconpilot.dataset import load_dataset
from siliconpilot.model import load_model,HardwareConfig
from siliconpilot.reference import quantize_input
from siliconpilot.verification import verify_model
from export_observatory import normalize_resources


def audit(root: Path,refresh: bool=True) -> dict:
    file=root/'benchmarks/corpus.json'
    records=json.loads(file.read_text())
    values,_=load_dataset(root,'validation')
    passed=[]
    for record in records:
        if not record.get('verified') or not record.get('routed'):
            continue
        directory=root/'benchmarks/runs'/record['id']
        build=json.loads((directory/'build.json').read_text())
        # The collector began before carry-inclusive field names were corrected.
        # This migration reads actual primitive counts; no new physical labels.
        normalize_resources(build)
        normalize_resources(record)
        for name,info in build['artifacts'].items():
            artifact=directory/name
            if hashlib.sha256(artifact.read_bytes()).hexdigest()!=info['sha256']:
                raise RuntimeError(f'Artifact digest mismatch {record["id"]}/{name}')
        cfg=HardwareConfig.from_dict(record['config'])
        width=record['dimensions'][1]
        model=load_model(root/f'models/banknote_4x{width}x2.json')
        if refresh:
            report=verify_model(model,cfg,directory,[quantize_input(row,cfg) for row in values])
        else:
            report=json.loads((directory/'verification.json').read_text())
        if report['rtl_sha256']!=build['rtl_sha256']:
            raise RuntimeError('Verified RTL differs from synthesized RTL')
        record['verification']=report
        record['accuracy_split']='validation'
        (directory/'candidate.json').write_text(json.dumps(record,indent=2)+'\n')
        (directory/'build.json').write_text(json.dumps(build,indent=2)+'\n')
        passed.append({'id':record['id'],'rtl_sha256':report['rtl_sha256'],'samples':report['samples'],
                       'artifact_digests_checked':len(build['artifacts']),'latency_cycles':report['latency_cycles']})
        print(f'AUDIT {record["id"]}: {report["samples"]} vectors; {record["lut"]} total mapped LUT4',flush=True)
    file.write_text(json.dumps(records,indent=2)+'\n')
    result={'schema_version':1,'candidates':len(records),'verified_and_routed':len(passed),
            'corpus_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
            'protocol_refresh':refresh,'checks':passed,
            'scope':'RTL verification linked by digest to synthesized/routed artifacts. No claim of DSP mapped netlist equivalence or physical hardware testing.'}
    (root/'benchmarks/audit.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--no-refresh',action='store_true')
    args=parser.parse_args()
    audit(args.root.resolve(),not args.no_refresh)
