"""Evaluate fixed validation-selected budget scenarios on reserved test rows."""
from __future__ import annotations
import json
from pathlib import Path
from siliconpilot.dataset import evaluate_accuracy,load_dataset
from siliconpilot.model import HardwareConfig,load_model
from siliconpilot.reference import quantize_input
from siliconpilot.verification import verify_model


def run(root: Path) -> dict:
    corpus=json.loads((root/'benchmarks/corpus.json').read_text())
    candidates=[r for r in corpus if r['model_id']=='banknote-4x8x2']
    scenarios=[{'name':'Compact logic budget','min_accuracy':.98,'max_lut':1200,'max_latency_us':3},
               {'name':'Balanced budget','min_accuracy':.98,'max_lut':1800,'max_latency_us':2},
               {'name':'Tight latency budget','min_accuracy':.98,'max_lut':2000,'max_latency_us':1}]
    model=load_model(root/'models/banknote_4x8x2.json')
    values,_=load_dataset(root,'test')
    results=[]
    for scenario in scenarios:
        feasible=[r for r in candidates if r['accuracy']>=scenario['min_accuracy'] and r['lut']<=scenario['max_lut']
                  and r['latency_cycles']/25<=scenario['max_latency_us'] and r['timing_met']]
        if not feasible:
            raise RuntimeError(f'No measured design meets {scenario}')
        candidate=min(feasible,key=lambda r:(r['latency_cycles'],-r['accuracy'],r['lut'],r['id']))
        cfg=HardwareConfig.from_dict(candidate['config'])
        accuracy=evaluate_accuracy(model,cfg,root,'test')
        verification=verify_model(model,cfg,root/'benchmarks/final-test'/candidate['id'],
                                  [quantize_input(row,cfg) for row in values])
        if verification['rtl_sha256']!=candidate['rtl_sha256']:
            raise RuntimeError('Final-test RTL differs from synthesized candidate')
        results.append({'scenario':scenario,'candidate_id':candidate['id'],'config':candidate['config'],
                        'validation_accuracy':candidate['accuracy'],'test':accuracy,
                        'verification':verification,'lut':candidate['lut'],'latency_cycles':candidate['latency_cycles'],
                        'fmax_mhz':candidate['fmax_mhz']})
    report={'schema_version':1,'selection':'lowest measured latency, then highest validation accuracy, then lowest LUT; main topology only',
            'scope':'Test rows evaluated after all architecture choices; never used by acquisition. No subsequent model/search tuning.',
            'results':results}
    (root/'benchmarks/final-test.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    run(Path.cwd())
