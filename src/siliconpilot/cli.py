"""One core, inspectable artifacts, explicit expensive operations."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any
from . import __version__
from .compiler import compile_model
from .model import HardwareConfig, load_model


def _hardware(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--bits',type=int,default=8)
    parser.add_argument('--fractional-bits',type=int,default=5)
    parser.add_argument('--accumulator-bits',type=int,default=24)
    parser.add_argument('--parallelism',type=int,default=1)
    parser.add_argument('--pipeline',action='store_true')
    parser.add_argument('--buffering',type=int,default=1)
    parser.add_argument('--config',type=Path,help='HardwareConfig JSON; replaces individual flags')


def _config(args: Any) -> HardwareConfig:
    if args.config:
        return HardwareConfig.from_dict(json.loads(args.config.read_text()))
    return HardwareConfig(bits=args.bits,fractional_bits=args.fractional_bits,
                          accumulator_bits=args.accumulator_bits,parallelism=args.parallelism,
                          pipeline=args.pipeline,buffering=args.buffering)


def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(prog='siliconpilot',description=__doc__)
    p.add_argument('--version',action='version',version=__version__)
    p.add_argument('--root',type=Path,default=Path.cwd(),help='Repository containing dataset/models/observatory')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor',help='Check free toolchain availability')
    sub.add_parser('train',help='Reproduce packaged sensor models')
    netlist=sub.add_parser('netlist',help='Independently simulate a saved synthesis result')
    netlist.add_argument('directory',type=Path)
    netlist.add_argument('--logic-only-out',type=Path,help='Build a distinct ECP5 LUT-only variant with upstream simulation models')
    formal=sub.add_parser('formal',help='Prove the tiny bounded arithmetic/protocol example')
    formal.add_argument('--out',type=Path,required=True)
    for name in ('compile','verify','build'):
        s=sub.add_parser(name)
        s.add_argument('model',type=Path)
        s.add_argument('--out',type=Path,required=True)
        _hardware(s)
        if name in ('verify','build'):
            s.add_argument('--dataset',action='store_true',help='Include packaged validation rows in differential simulation')
        if name=='build':
            s.add_argument('--synthesis-only',action='store_true')
            s.add_argument('--clock-mhz',type=float,default=25.)
    for name in ('search','replay'):
        s=sub.add_parser(name)
        s.add_argument('--out',type=Path,required=True)
        s.add_argument('--min-accuracy',type=float,default=.98)
        s.add_argument('--max-lut',type=int,default=3000)
        s.add_argument('--max-latency-us',type=float,default=5.)
        s.add_argument('--budget-seconds',type=float)
        if name=='search':
            s.add_argument('model',type=Path)
            s.add_argument('--evaluations',type=int,default=12)
            s.add_argument('--seed',type=int,default=0)
            s.add_argument('--validation-data',type=Path,help='Standardized {inputs:[[...]],labels:[...]} JSON for imported model')
        else:
            s.add_argument('--corpus',type=Path,required=True)
            s.add_argument('--seeds',type=int,default=5)
            s.add_argument('--train-model-id',default='banknote-4x8x2')
    serve=sub.add_parser('serve',help='Loopback observatory plus actual compiler API')
    serve.add_argument('--port',type=int,default=8791)
    return p


def main() -> None:
    args=parser().parse_args()
    try:
        if args.command=='doctor':
            names=('iverilog','vvp','yosys','nextpnr-ecp5')
            result={'version':__version__,'python':sys.version.split()[0],
                    'tools':{name:shutil.which(name) for name in names},
                    'dataset_present':(args.root/'data/banknote.csv').is_file()}
            print(json.dumps(result,indent=2))
            if not all(result['tools'].values()):
                sys.exit(1)
            return
        if args.command=='train':
            from .dataset import train_models
            result=train_models(args.root)
        elif args.command=='formal':
            from .formal import prove_tiny
            result=prove_tiny(args.out)
        elif args.command=='netlist':
            from .netlist import run_netlist_verification,prepare_logic_only_build
            directory=args.directory
            if args.logic_only_out:
                prepare_logic_only_build(directory,args.logic_only_out,route=True)
                directory=args.logic_only_out
            result=run_netlist_verification(directory)
        elif args.command in ('compile','verify','build'):
            model=load_model(args.model)
            cfg=_config(args)
            if args.command=='compile':
                result=compile_model(model,cfg,args.out)
            else:
                from .verification import verify_model
                vectors=None
                if args.dataset:
                    from .dataset import load_dataset
                    from .reference import quantize_input
                    values,_=load_dataset(args.root,'validation')
                    vectors=[quantize_input(row,cfg) for row in values]
                verification=verify_model(model,cfg,args.out,vectors=vectors)
                result=verification
                if args.command=='build':
                    from .toolchain import run_build
                    result={'verification':verification,'build':run_build(model,cfg,args.out,route=not args.synthesis_only,clock_mhz=args.clock_mhz)}
        elif args.command in ('search','replay'):
            from .search import Budgets, optimize, run_experiments
            budgets=Budgets(min_accuracy=args.min_accuracy,max_lut=args.max_lut,max_latency_us=args.max_latency_us)
            if args.command=='replay':
                if args.seeds<1:
                    raise ValueError('--seeds must be positive')
                result=run_experiments(json.loads(args.corpus.read_text()),args.out,
                                       budget_seconds=args.budget_seconds,seeds=range(args.seeds),
                                       budgets=budgets,train_model_id=args.train_model_id)
            else:
                configs=[HardwareConfig(bits=b,fractional_bits=b-3,accumulator_bits=2*b+8,parallelism=n,pipeline=pipe)
                         for b in (4,6,8) for n in (1,2,4) for pipe in (False,True)]
                callback=None
                if args.validation_data:
                    from .model import quantize
                    from .reference import evaluate_integer,quantize_input
                    dataset=json.loads(args.validation_data.read_text())
                    inputs,labels=dataset['inputs'],dataset['labels']
                    if not inputs or len(inputs)!=len(labels):
                        raise ValueError('Validation inputs/labels must be nonempty and equal length')
                    def callback(model: Any,cfg: HardwareConfig) -> float:
                        q=quantize(model,cfg)
                        correct=0
                        for row,label in zip(inputs,labels):
                            scores=evaluate_integer(q,quantize_input(row,cfg))
                            correct+=max(range(len(scores)),key=scores.__getitem__)==label
                        return correct/len(labels)
                result=optimize(load_model(args.model),configs,args.root,args.out,budgets=budgets,
                                max_evaluations=args.evaluations,budget_seconds=args.budget_seconds or 600.,
                                seed=args.seed,accuracy_fn=callback)
        else:
            from .server import serve
            serve(args.root,args.port)
            return
        print(json.dumps(result,indent=2))
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as exc:
        print(f'siliconpilot: {exc}',file=sys.stderr)
        sys.exit(2)


if __name__=='__main__':
    main()
