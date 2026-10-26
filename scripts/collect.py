"""Compile a predetermined design corpus; never substitute predicted labels."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import time
from siliconpilot.dataset import evaluate_accuracy, load_dataset
from siliconpilot.model import HardwareConfig, load_model
from siliconpilot.reference import quantize_input
from siliconpilot.toolchain import run_build
from siliconpilot.verification import verify_model


def configurations() -> list[HardwareConfig]:
    # A finite, preregistered coverage corpus, not a claim of exhaustive search.
    base = [HardwareConfig(bits=b, fractional_bits=b-3, accumulator_bits=2*b+8,
                           parallelism=p, pipeline=pipe, buffering=1)
            for b in (4,6,8) for p in (1,2,4) for pipe in (False, True)]
    base += [HardwareConfig(bits=b, fractional_bits=b-3, accumulator_bits=2*b,
                            parallelism=p, pipeline=False, buffering=2)
             for b in (4,6,8) for p in (1,4)]
    return base


def collect(root: Path, workers: int = 2, limit: int | None = None,
            output: Path | None = None, resume: bool = False) -> None:
    if workers < 1 or (limit is not None and limit < 1):
        raise ValueError('workers and limit must be positive')
    configs = configurations()
    jobs = [(8,i,c) for i,c in enumerate(configs)]
    # Two completely held-out topologies, paired hardware settings.
    jobs += [(width,i,configs[i]) for width in (4,12) for i in (0,3,6,9,12,15,18,21)]
    if limit is not None:
        jobs = jobs[:limit]
    corpus_dir = output or root/'benchmarks/reproduced'
    if not corpus_dir.is_absolute():
        corpus_dir=root/corpus_dir
    if corpus_dir.exists() and any(corpus_dir.iterdir()) and not resume:
        raise ValueError('Output already contains evidence; choose a new --output or explicitly --resume')
    corpus_dir.mkdir(parents=True,exist_ok=True)
    protocol = {'schema_version':1, 'main_width':8, 'heldout_widths':[4,12],
                'candidate_count':len(jobs),'configs':[asdict(c) for c in configs],
                'workers':workers,'clock_mhz':25,'routing_seed':1,
                'note':'Predetermined finite coverage corpus, not exhaustive. Costs are wall time per process under this documented concurrency. Search replay uses validation accuracy only.'}
    (corpus_dir/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    features,_ = load_dataset(root,'validation')
    def job(width: int, index: int, config: HardwareConfig) -> dict:
        candidate_id=f'w{width}-c{index:02d}'
        directory=corpus_dir/'runs'/candidate_id
        record_file=directory/'candidate.json'
        model=load_model(root/f'models/banknote_4x{width}x2.json')
        if record_file.exists():
            existing=json.loads(record_file.read_text())
            if existing.get('verified') and existing.get('routed'):
                model_hash=hashlib.sha256(json.dumps(model,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                if existing.get('model_sha256')!=model_hash or existing.get('config')!=asdict(config):
                    raise ValueError(f'{candidate_id}: saved model/config differs; use a fresh output')
                build=json.loads((directory/'build.json').read_text())
                for name,info in build['artifacts'].items():
                    path=directory/name
                    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:
                        raise ValueError(f'{candidate_id}: cached artifact missing or changed: {name}; use a fresh output')
                return existing
        directory.mkdir(parents=True,exist_ok=True)
        accuracy=evaluate_accuracy(model,config,root,'validation')
        vectors=[quantize_input(row,config) for row in features]
        try:
            verification=verify_model(model,config,directory,vectors=vectors)
            report=run_build(model,config,directory,route=True)
            record={'id':candidate_id,'model_id':f'banknote-4x{width}x2',
                    'model_width':width,'config_index':index,
                    'accuracy':accuracy['accuracy'],'validation':accuracy,
                    'verified':verification['passed'],'verification':verification,
                    **report}
        except Exception as exc:
            record={'id':candidate_id,'model_id':f'banknote-4x{width}x2',
                    'config':asdict(config),'verified':False,'routed':False,'error':str(exc)}
        record_file.write_text(json.dumps(record,indent=2)+'\n')
        return record
    records=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(job,*args):args for args in jobs}
        for future in as_completed(futures):
            record=future.result()
            records.append(record)
            records.sort(key=lambda r:r['id'])
            (corpus_dir/'corpus.json').write_text(json.dumps(records,indent=2)+'\n')
            print(json.dumps({'completed':len(records),'total':len(jobs),'id':record['id'],
                              'verified':record['verified'],'routed':record['routed'],
                              'lut':record.get('lut'),'fmax':record.get('fmax_mhz'),
                              'seconds':record.get('compile_seconds'),'error':record.get('error')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--limit',type=int)
    parser.add_argument('--output',type=Path,default=Path('benchmarks/reproduced'))
    parser.add_argument('--resume',action='store_true',help='Resume only hash-validated existing full builds')
    args=parser.parse_args()
    collect(args.root.resolve(),args.workers,args.limit,args.output,args.resume)
