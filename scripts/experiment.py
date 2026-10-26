#!/usr/bin/env python3
"""Run honest measured-corpus search replays; never generates FPGA metrics."""
import argparse
import hashlib
import json
from pathlib import Path
from siliconpilot.search import Budgets, run_experiments


LABELS = {
    "cost_aware":"RF · cost + two fidelities", "random":"Random search", "fixed":"Fixed architecture sweep",
    "fixed_serial":"Fixed serial family", "fixed_parallel":"Fixed parallel family", "gp_ehvi":"Gaussian process · EHVI",
    "no_uncertainty":"Ablation · mean-only acquisition", "no_cost":"Ablation · no cost normalization",
    "no_low_fidelity":"Ablation · route only",
}


def plot_results(results_dir: Path, figures_dir: Path) -> None:
    """Quantitative figures are derived exclusively from saved measured reports."""
    import os
    import tempfile
    os.environ.setdefault("MPLCONFIGDIR",str(Path(tempfile.gettempdir())/"siliconpilot-matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    experiment_path = results_dir/"experiments.json"
    surrogate_path = results_dir/"surrogate_metadata.json"
    result=json.loads(experiment_path.read_text())
    metadata=json.loads(surrogate_path.read_text())
    figures_dir.mkdir(parents=True,exist_ok=True)
    ink="#1e2c32"
    orange="#d85c33"
    slate="#657983"
    paper="#f5f2e9"
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"text.color":ink,"axes.labelcolor":ink,
                         "xtick.color":ink,"ytick.color":ink,"axes.edgecolor":"#bbc3c2","axes.spines.top":False,
                         "axes.spines.right":False,"figure.facecolor":paper,"axes.facecolor":paper,"svg.fonttype":"none"})
    fig,ax=plt.subplots(figsize=(11,6.7))
    rows=result["summary"]
    y=np.arange(len(rows))
    reference=result["reference_hypervolume"]
    if reference > 0:
        means=[r["hypervolume_mean"]/reference for r in rows]
        errors=[r["hypervolume_std"]/reference for r in rows]
        xlabel="Fraction of the finite-pool reference hypervolume · higher is better"
    else:
        means=[r["hypervolume_mean"] for r in rows]
        errors=[r["hypervolume_std"] for r in rows]
        xlabel="Feasible dominated hypervolume · higher is better"
    ax.barh(y,means,xerr=errors,color=[orange if r["strategy"]=="cost_aware" else slate for r in rows],height=.58,
            error_kw={"ecolor":ink,"capsize":3,"elinewidth":1})
    ax.set_yticks(y,[LABELS[r["strategy"]] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0,1.16 if reference > 0 else 1.)
    ax.set_xlabel(xlabel,labelpad=12)
    ax.grid(axis="x",alpha=.2)
    ax.set_axisbelow(True)
    for i,(mean,row) in enumerate(zip(means,rows)):
        ax.text(min(mean+errors[i]+.015,1.04),i,f"{100*mean:.1f}%" if reference > 0 else f"{mean:.3f}",va="center",fontsize=9)
    fig.suptitle("SILICONPILOT / MEASURED-COST SEARCH",x=.03,y=.985,ha="left",fontsize=16,fontweight="bold")
    b=result["constraints"]
    fig.text(.03,.935,f"{result['candidate_count']} routed designs · {rows[0]['seeds']} seeds · {result['budget_seconds']:.1f} s common FPGA-tool budget",fontsize=10)
    fig.text(.03,.895,f"Validation accuracy ≥ {100*b['min_accuracy']:g}%   /   LUTs ≤ {b['max_lut']}   /   core latency ≤ {b['max_latency_us']:g} μs at {b['clock_mhz']:g} MHz",fontsize=9)
    fig.text(.03,.025,"Bars: mean ± sample standard deviation. Offline finite-pool replay; acquisition CPU time reported separately.\nRecorded synthesis/routing costs; target-clock estimates, no physical FPGA measurements.",fontsize=8,color=slate)
    fig.subplots_adjust(left=.34,right=.96,top=.85,bottom=.15)
    for suffix in ("svg","png"):
        fig.savefig(figures_dir/f"search-comparison.{suffix}",dpi=170,bbox_inches="tight")
    plt.close(fig)

    fig,axes=plt.subplots(2,2,figsize=(11,8))
    labels={"lut":"Mapped LUT4 count","fmax_mhz":"Routed fmax estimate / MHz",
            "synthesis_seconds":"Synthesis wall time / s","route_seconds":"Routing wall time / s"}
    for ax,(target,statistics) in zip(axes.flat,metadata["evaluation"].items()):
        entries=statistics["predictions"]
        actual=np.asarray([r["actual"] for r in entries])
        predicted=np.asarray([r["mean"] for r in entries])
        lo=np.asarray([r["p05"] for r in entries])
        hi=np.asarray([r["p95"] for r in entries])
        colors=[orange if r["id"].startswith("w4-") else slate for r in entries]
        ax.vlines(actual,lo,hi,color="#a8b1ad",alpha=.8,lw=.8,zorder=1)
        ax.scatter(actual,predicted,c=colors,s=32,edgecolors=paper,linewidth=.6,zorder=2)
        low=min(actual.min(),lo.min())*.85
        high=max(actual.max(),hi.max())*1.1
        ax.plot([low,high],[low,high],color=ink,lw=1,ls="--",alpha=.6)
        ax.set_xlim(low,high)
        ax.set_ylim(low,high)
        ax.set_xlabel("Actual · "+labels[target])
        ax.set_ylabel("Surrogate prediction")
        ax.set_title(f"MAE {statistics['mean_absolute_error']:.2f}   |   nominal 90% coverage {100*statistics['nominal_90_interval_coverage']:.0f}%",fontsize=9,loc="left")
        ax.grid(alpha=.15)
    fig.suptitle("SILICONPILOT / UNSEEN NETWORK CONFIGURATIONS",x=.03,y=.99,ha="left",fontsize=15,fontweight="bold")
    fig.text(.03,.947,f"Train: {metadata['train_model_id']} ({len(metadata['train_ids'])} designs) · held-out: {', '.join(metadata['heldout_model_ids'])}",fontsize=9)
    fig.text(.03,.015,"Orange: width 4. Slate: width 12. Error bars: ensemble 5th–95th percentiles. The diagonal is perfect prediction.\nApproximate tree uncertainty is not a calibrated confidence guarantee; all labels come from real compiler runs.",fontsize=8,color=slate)
    fig.subplots_adjust(left=.08,right=.97,top=.88,bottom=.12,hspace=.47,wspace=.28)
    for suffix in ("svg","png"):
        fig.savefig(figures_dir/f"surrogate-generalization.{suffix}",dpi=170,bbox_inches="tight")
    plt.close(fig)
    (figures_dir/"search-figures-manifest.json").write_text(json.dumps({"sources":{
        str(experiment_path):hashlib.sha256(experiment_path.read_bytes()).hexdigest(),
        str(surrogate_path):hashlib.sha256(surrogate_path.read_bytes()).hexdigest()},
        "figures":["search-comparison.svg","search-comparison.png","surrogate-generalization.svg","surrogate-generalization.png"]},indent=2)+"\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus",type=Path)
    parser.add_argument("--output",type=Path,default=Path("benchmarks/search"))
    parser.add_argument("--budget-seconds",type=float)
    parser.add_argument("--seeds",type=int,default=5)
    parser.add_argument("--min-accuracy",type=float,default=.90)
    parser.add_argument("--max-lut",type=int,default=3000)
    parser.add_argument("--max-latency-us",type=float,default=15.)
    parser.add_argument("--clock-mhz",type=float,default=25.)
    parser.add_argument("--train-model-id",default="banknote-4x8x2")
    parser.add_argument("--figures",type=Path,default=Path("docs/assets"))
    parser.add_argument("--plot-only",action="store_true")
    args = parser.parse_args()
    if not args.plot_only:
        data = json.loads(args.corpus.read_text())
        records = data if isinstance(data,list) else data["candidates"]
        result = run_experiments(records,args.output,budget_seconds=args.budget_seconds,seeds=tuple(range(args.seeds)),
                                 budgets=Budgets(args.min_accuracy,args.max_lut,args.max_latency_us,args.clock_mhz),
                                 train_model_id=args.train_model_id)
        print(json.dumps({"evaluation":result["evaluation"],"budget_seconds":result["budget_seconds"],"summary":result["summary"]},indent=2),flush=True)
    plot_results(args.output,args.figures)


if __name__ == "__main__":
    main()
