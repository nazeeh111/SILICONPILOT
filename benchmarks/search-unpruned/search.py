"""Measured-data surrogate and cost-aware, two-fidelity FPGA design search.

Only integer-reference accuracy and analytic cycle counts are free information.
LUT counts appear after synthesis; routed timing appears after place-and-route.
The replay evaluator reveals these labels only after each paid evaluation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence
import warnings

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.exceptions import ConvergenceWarning

FEATURE_NAMES = ["inputs", "hidden", "outputs", "layers", "macs", "parameters", "bits", "fractional_bits",
                 "accumulator_bits", "parallelism", "pipeline", "buffering", "cycles"]
TARGETS = ("lut", "fmax_mhz", "synthesis_seconds", "route_seconds")
STRATEGIES = ("cost_aware", "random", "fixed", "fixed_serial", "fixed_parallel", "gp_ehvi", "no_uncertainty", "no_cost", "no_low_fidelity")


@dataclass(frozen=True)
class Budgets:
    min_accuracy: float = 0.90
    max_lut: int = 3000
    max_latency_us: float = 15.0
    clock_mhz: float = 25.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(float(v)) for v in (self.min_accuracy,self.max_lut,self.max_latency_us,self.clock_mhz)) or not 0 < self.min_accuracy <= 1 or self.max_lut <= 0 or self.max_latency_us <= 0 or self.clock_mhz <= 0:
            raise ValueError("Accuracy must be in (0,1]; LUT, latency and clock budgets must be positive")


def features(record: Mapping[str, Any]) -> list[float]:
    """Features known before HDL synthesis, never measured target labels."""
    dims = record.get("dimensions", [4, 8, 2])
    if not isinstance(dims, (list, tuple)) or len(dims) < 2 or min(dims) <= 0:
        raise ValueError("dimensions must list positive layer widths")
    c = record["config"]
    macs = sum(a * b for a, b in zip(dims, dims[1:]))
    params = macs + sum(dims[1:])
    return [float(v) for v in (dims[0], max(dims[1:-1], default=0), dims[-1], len(dims)-1,
                               macs, params, c["bits"], c["fractional_bits"], c["accumulator_bits"],
                               c["parallelism"], c.get("pipeline", False), c.get("buffering", 1), record["latency_cycles"])]


def normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Accept the flat public corpus schema; reject missing actual measurements."""
    out = dict(record)
    for key in ("id", "model_id", "config", "dimensions", "accuracy", "latency_cycles"):
        if key not in out:
            raise ValueError(f"Corpus record is missing {key}")
    for key in (*TARGETS, "ff"):
        if key not in out or not math.isfinite(float(out[key])) or float(out[key]) <= 0:
            raise ValueError(f"Corpus record {out['id']} needs a positive measured {key}")
        out[key] = float(out[key])
    if not 0 <= out["accuracy"] <= 1:
        raise ValueError("accuracy must be a validation fraction in [0,1]")
    if out.get("accuracy_split", "validation") != "validation":
        raise ValueError("Search must use validation accuracy, never test accuracy")
    if out.get("verified", False) is not True or out.get("routed", False) is not True:
        raise ValueError("Replay corpus must contain verified, successfully routed candidates")
    out["compile_seconds"] = out["synthesis_seconds"] + out["route_seconds"]
    features(out)
    return out


def public_candidate(record: Mapping[str, Any]) -> dict[str, Any]:
    """Information supplied to acquisition before any paid query."""
    return {key: record[key] for key in ("id", "model_id", "config", "dimensions", "accuracy", "latency_cycles")}


def latency_us(record: Mapping[str, Any], fmax_mhz: float, clock_mhz: float) -> float:
    # A target-clock miss is infeasible, rather than quietly using a slower clock.
    return float(record["latency_cycles"]) / clock_mhz if fmax_mhz >= clock_mhz else math.inf


def objective_point(record: Mapping[str, Any], budgets: Budgets) -> tuple[float, float, float] | None:
    accuracy = float(record["accuracy"])
    latency = latency_us(record, float(record["fmax_mhz"]), budgets.clock_mhz)
    lut = float(record["lut"])
    if accuracy < budgets.min_accuracy or lut > budgets.max_lut or latency > budgets.max_latency_us:
        return None
    return ((1-accuracy)/max(1-budgets.min_accuracy,1e-12), latency/budgets.max_latency_us, lut/budgets.max_lut)


def pareto_front(records: Sequence[Mapping[str, Any]], budgets: Budgets | None = None) -> list[str]:
    """Three objectives: maximize accuracy; minimize cycles and measured LUT."""
    valid = [r for r in records if budgets is None or objective_point(r, budgets) is not None]
    result: list[str] = []
    for r in valid:
        p = (1-float(r["accuracy"]), float(r["latency_cycles"]), float(r["lut"]))
        dominated = False
        for s in valid:
            q = (1-float(s["accuracy"]), float(s["latency_cycles"]), float(s["lut"]))
            if all(a <= b for a,b in zip(q,p)) and any(a < b for a,b in zip(q,p)):
                dominated = True
                break
        if not dominated:
            result.append(str(r["id"]))
    return result


def hypervolume(points: Sequence[Sequence[float]]) -> float:
    """Exact dominated volume in a [0,1]^3 minimization box."""
    pts = sorted(set(tuple(float(v) for v in p) for p in points if len(p) == 3 and all(0 <= v < 1 for v in p)))
    total = 0.0
    for index, p in enumerate(pts):
        x = p[0]
        next_x = pts[index+1][0] if index+1 < len(pts) else 1.0
        if next_x <= x:
            continue
        yz = sorted(set((q[1],q[2]) for q in pts if q[0] <= x))
        area = 0.0
        min_z = 1.0
        for j,(y,z) in enumerate(yz):
            min_z = min(min_z,z)
            next_y = yz[j+1][0] if j+1 < len(yz) else 1.0
            area += (next_y-y)*(1-min_z)
        total += (next_x-x)*area
    return float(total)


def score(records: Sequence[Mapping[str, Any]], budgets: Budgets) -> float:
    return hypervolume([p for r in records if (p := objective_point(r,budgets)) is not None])


class CostSurrogate:
    """Random-forest ensemble in log space; tree spread is uncertainty, not a guarantee."""
    def __init__(self, seed: int = 0, trees: int = 48) -> None:
        self.seed = seed
        self.trees = trees
        self.models: dict[str, RandomForestRegressor] = {}
        self.train_counts: dict[str,int] = {}

    def fit(self, observations: Sequence[Mapping[str, Any]]) -> CostSurrogate:
        self.models.clear()
        for target in TARGETS:
            known = [r for r in observations if target in r and math.isfinite(float(r[target])) and float(r[target]) > 0]
            self.train_counts[target] = len(known)
            if len(known) >= 2:
                estimator = RandomForestRegressor(n_estimators=self.trees, min_samples_leaf=1, max_features=1.0,
                                                  random_state=self.seed, n_jobs=1)
                estimator.fit(np.asarray([features(r) for r in known]), np.log([r[target] for r in known]))
                self.models[target] = estimator
        return self

    def predict_log(self, pool: Sequence[Mapping[str, Any]], samples: int = 16) -> np.ndarray:
        """Return [candidate, Monte Carlo draw, target] without reading hidden labels."""
        if not pool:
            return np.empty((0,samples,len(TARGETS)))
        x = np.asarray([features(r) for r in pool])
        rng = np.random.default_rng(self.seed + 2718)
        draws = np.empty((len(pool),samples,len(TARGETS)))
        for j,target in enumerate(TARGETS):
            model = self.models.get(target)
            if model is not None:
                prediction = np.asarray([tree.predict(x) for tree in model.estimators_]).T
                choices = rng.integers(0, prediction.shape[1], samples)
                # Floor avoids falsely certain acquisition outside a tiny forest's training set.
                draws[:,:,j] = prediction[:,choices] + rng.normal(0,0.05,(len(pool),samples))
            else:
                # Transparent physics-inspired cold prior, no corpus labels.
                if target == "lut":
                    base = np.asarray([100 + 3*r["config"]["bits"]*r["config"]["parallelism"] + 2*sum(r["dimensions"]) for r in pool])
                elif target == "fmax_mhz":
                    base = np.full(len(pool),45.)
                elif target == "synthesis_seconds":
                    base = np.full(len(pool),5.)
                else:
                    base = np.full(len(pool),10.)
                draws[:,:,j] = np.log(base)[:,None] + rng.normal(0,0.35,(len(pool),samples))
        return draws


class GPSurrogate:
    """Conventional independent Matérn Gaussian processes for EHVI baseline."""
    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.models: dict[str,GaussianProcessRegressor] = {}
        self.fallback = CostSurrogate(seed=seed)
        self.center: np.ndarray | None = None
        self.scale: np.ndarray | None = None

    def fit(self, observations: Sequence[Mapping[str, Any]]) -> GPSurrogate:
        self.fallback.fit(observations)
        if observations:
            xx = np.asarray([features(r) for r in observations])
            self.center = xx.mean(axis=0)
            self.scale = np.maximum(xx.std(axis=0),1.)
        for target in TARGETS:
            known = [r for r in observations if target in r and float(r[target]) > 0]
            if len(known) >= 3:
                x = (np.asarray([features(r) for r in known])-self.center)/self.scale
                kernel = ConstantKernel(1.,(0.05,20.))*Matern(length_scale=1.,length_scale_bounds=(0.05,20.),nu=2.5)+WhiteKernel(0.01,(1e-5,0.2))
                gp = GaussianProcessRegressor(kernel=kernel,normalize_y=True,random_state=self.seed,alpha=1e-6,n_restarts_optimizer=0)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore",ConvergenceWarning)
                    gp.fit(x,np.log([r[target] for r in known]))
                self.models[target] = gp
        return self

    def predict_log(self,pool: Sequence[Mapping[str,Any]],samples: int=16) -> np.ndarray:
        output = self.fallback.predict_log(pool,samples)
        if not self.models:
            return output
        x = (np.asarray([features(r) for r in pool])-self.center)/self.scale
        rng = np.random.default_rng(self.seed + 2718)
        for j,target in enumerate(TARGETS):
            if target in self.models:
                mean,std = self.models[target].predict(x,return_std=True)
                output[:,:,j] = mean[:,None]+rng.normal(0,1,(len(pool),samples))*np.maximum(std[:,None],0.05)
        return output


def propose(pool: Sequence[Mapping[str,Any]], observations: Sequence[Mapping[str,Any]], *, budgets: Budgets = Budgets(),
            strategy: str = "cost_aware", seed: int = 0) -> dict[str, Any] | None:
    """Select next synthesis or routing query, consuming only revealed observations.

    Pool must contain only public_candidate fields. Partial observations after
    synthesis contain LUT/FF and synthesis_seconds; route observations also
    contain fmax_mhz and route_seconds. This API also drives an online caller.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy {strategy}; choose from {STRATEGIES}")
    observed = {str(r["id"]):dict(r) for r in observations}
    remaining = [r for r in pool if str(r["id"]) not in observed or "fmax_mhz" not in observed[str(r["id"])]]
    # Low-accuracy designs can never satisfy the advertised accuracy constraint.
    remaining = [r for r in remaining if float(r["accuracy"]) >= budgets.min_accuracy]
    if not remaining:
        return None
    completed = [r for r in observations if "fmax_mhz" in r]
    rng = np.random.default_rng(seed + 7919*len(observations) + 17*len(completed))
    if strategy == "random":
        chosen = remaining[int(rng.integers(len(remaining)))]
        return {"candidate_id":chosen["id"],"fidelity":"route","acquisition":None}
    if strategy in ("fixed", "fixed_serial", "fixed_parallel"):
        if strategy != "fixed":
            lanes = 1 if strategy == "fixed_serial" else max(r["config"]["parallelism"] for r in pool)
            remaining = [r for r in remaining if r["config"]["parallelism"] == lanes
                         and not r["config"].get("pipeline",False) and r["config"].get("buffering",1) == 1]
            if not remaining:
                return None
        # Predetermined conventional Q3.5, serial-first ordering. No target labels.
        def fixed_order(r: Mapping[str,Any]) -> tuple[float,...]:
            c = r["config"]
            return (abs(c["bits"]-8),abs(c["fractional_bits"]-5),c["pipeline"],c["buffering"],c["parallelism"],abs(c["accumulator_bits"]-24))
        chosen = min(remaining,key=fixed_order)
        return {"candidate_id":chosen["id"],"fidelity":"route","acquisition":None}
    # Identical seeded random warm start for learned strategies.
    if len(completed) < 3:
        untried = [r for r in remaining if r["id"] not in observed]
        chosen = (untried or remaining)[int(rng.integers(len(untried or remaining)))]
        return {"candidate_id":chosen["id"],"fidelity":"route","acquisition":None,"reason":"common seeded warm start"}
    surrogate = (GPSurrogate(seed) if strategy == "gp_ehvi" else CostSurrogate(seed)).fit(observations)
    draws = np.exp(np.clip(surrogate.predict_log(remaining),-12,20))
    screening_draws = draws.copy()
    if strategy == "no_uncertainty":
        draws[:] = draws.mean(axis=1,keepdims=True)
    current_points = [p for r in completed if (p := objective_point(r,budgets)) is not None]
    current_score = hypervolume(current_points)
    best: dict[str,Any] | None = None
    for i,candidate in enumerate(remaining):
        prior = observed.get(str(candidate["id"]),{})
        if "lut" in prior:
            draws[i,:,0] = prior["lut"]
        expected_gain = 0.0
        probability_feasible = 0.0
        for lut,fmax,_,_ in draws[i]:
            predicted = dict(candidate,lut=float(lut),fmax_mhz=float(fmax))
            point = objective_point(predicted,budgets)
            if point is not None:
                probability_feasible += 1/len(draws[i])
                expected_gain += max(0.,hypervolume([*current_points,point])-current_score)/len(draws[i])
        synth_cost = float(draws[i,:,2].mean())
        route_cost = float(draws[i,:,3].mean())
        is_synthesized = "lut" in prior
        fidelity = "route"
        if strategy not in ("gp_ehvi","no_low_fidelity") and not is_synthesized:
            # Screen resource feasibility cheaply before committing to routing.
            # Synthesis is valuable when its cost is lower than routing and its
            # resource posterior has mass on both sides of the resource limit.
            p_resource = float(np.mean(screening_draws[i,:,0] <= budgets.max_lut))
            resource_entropy = 4*p_resource*(1-p_resource)
            relative_spread = float(np.std(screening_draws[i,:,0])/max(np.mean(screening_draws[i,:,0]),1.))
            if synth_cost < route_cost and (resource_entropy > 0.1 or relative_spread > 0.05):
                fidelity = "synthesis"
        cost = route_cost + (0. if is_synthesized else synth_cost) if fidelity == "route" else synth_cost
        # Small information bonus keeps discovery moving when current observed
        # front dominates posterior means; no hidden results enter this term.
        info = float(np.std(draws[i,:,0])/max(np.mean(draws[i,:,0]),1.))
        acquisition = expected_gain + 0.0002*probability_feasible*info
        if strategy not in ("no_cost","gp_ehvi"):
            acquisition /= max(cost,1e-3)
        if fidelity == "synthesis":
            acquisition *= 0.5 # conservative screening credit, ablated explicitly
        if best is None or acquisition > best["acquisition"]:
            best = {"candidate_id":candidate["id"],"fidelity":fidelity,"acquisition":float(acquisition),
                    "predicted_cost_seconds":cost,"expected_hypervolume_gain":expected_gain,
                    "predicted_feasible_probability":probability_feasible}
    return best


def replay(records: Sequence[Mapping[str,Any]], *, budget_seconds: float, strategy: str,
           seed: int = 0, budgets: Budgets = Budgets()) -> dict[str,Any]:
    """Offline finite-pool replay, censored at a common measured-compute budget."""
    if not math.isfinite(budget_seconds) or budget_seconds <= 0:
        raise ValueError("budget_seconds must be finite and positive")
    corpus = {str(r["id"]):normalize_record(r) for r in records}
    if len(corpus) != len(records):
        raise ValueError("Candidate ids must be unique")
    pool = [public_candidate(r) for r in corpus.values()]
    observations: dict[str,dict[str,Any]] = {}
    elapsed = 0.0
    acquisition_seconds = 0.0
    history: list[dict[str,Any]] = []
    censored: dict[str,Any] | None = None
    # Each design can be queried once at synthesis and once at route fidelity.
    for _ in range(2*len(pool)):
        start = time.perf_counter()
        action = propose(pool,list(observations.values()),budgets=budgets,strategy=strategy,seed=seed)
        acquisition_seconds += time.perf_counter()-start
        if action is None:
            break
        record = corpus[str(action["candidate_id"])]
        previous = observations.get(str(record["id"]),{})
        cost = record["route_seconds"] if action["fidelity"] == "route" and "lut" in previous else (
            record["synthesis_seconds"] if action["fidelity"] == "synthesis" else record["compile_seconds"])
        if elapsed+cost > budget_seconds:
            # End this run. Neither this query's labels nor alternative cheaper
            # candidates are revealed. Noninterruptible overrun is recorded.
            censored = {"candidate_id":record["id"],"fidelity":action["fidelity"],"would_finish_at_seconds":elapsed+cost}
            break
        elapsed += cost
        revealed = dict(public_candidate(record),lut=record["lut"],ff=record["ff"],synthesis_seconds=record["synthesis_seconds"])
        if action["fidelity"] == "route":
            revealed.update(fmax_mhz=record["fmax_mhz"],route_seconds=record["route_seconds"])
        observations[str(record["id"])] = revealed
        routed = [r for r in observations.values() if "fmax_mhz" in r]
        history.append(dict(action,iteration=len(history)+1,elapsed_seconds=elapsed,evaluation_seconds=cost,
                            hypervolume=score(routed,budgets),routed_candidates=len(routed)))
    routed = [r for r in observations.values() if "fmax_mhz" in r]
    return {"strategy":strategy,"seed":seed,"budget_seconds":budget_seconds,"completed_compile_seconds":elapsed,
            "acquisition_wall_seconds":acquisition_seconds,"hypervolume":score(routed,budgets),"pareto_ids":pareto_front(routed,budgets),
            "routed_candidates":len(routed),"synthesis_only_candidates":len(observations)-len(routed),
            "censored_query":censored,"history":history}


def train_surrogate(records: Sequence[Mapping[str,Any]], output_dir: str | Path,
                    train_model_id: str = "banknote-4x8x2") -> dict[str,Any]:
    """Train on one topology; evaluate all *other* network configurations."""
    import joblib
    import sklearn
    import hashlib
    out = Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    records = [normalize_record(r) for r in records]
    train = [r for r in records if r["model_id"] == train_model_id]
    test = [r for r in records if r["model_id"] != train_model_id]
    if len(train) < 3:
        raise ValueError("At least three measured records of train_model_id are required")
    estimator = CostSurrogate(seed=20261025,trees=96).fit(train)
    evaluation: dict[str,Any] = {}
    if test:
        draws = np.exp(estimator.predict_log([public_candidate(r) for r in test],samples=96))
        for j,target in enumerate(TARGETS):
            actual = np.asarray([r[target] for r in test])
            predictions = draws[:,:,j].mean(axis=1)
            low,high = np.quantile(draws[:,:,j],[.05,.95],axis=1)
            baseline = np.full(len(test),np.mean([r[target] for r in train]))
            evaluation[target] = {"mean_absolute_error":float(np.mean(np.abs(predictions-actual))),
                                  "mean_absolute_percentage_error":float(np.mean(np.abs(predictions-actual)/actual)),
                                  "mean_baseline_absolute_error":float(np.mean(np.abs(baseline-actual))),
                                  "nominal_90_interval_coverage":float(np.mean((actual>=low)&(actual<=high))),
                                  "predictions":[{"id":r["id"],"actual":float(a),"mean":float(p),"p05":float(l),"p95":float(h)} for r,a,p,l,h in zip(test,actual,predictions,low,high)]}
    joblib.dump(estimator,out/"surrogate.joblib",compress=3)
    metadata = {"schema_version":1,"kind":"random_forest_log_target_ensemble","features":FEATURE_NAMES,
                "targets":list(TARGETS),"train_model_id":train_model_id,"train_ids":[r["id"] for r in train],
                "heldout_model_ids":sorted(set(r["model_id"] for r in test)),"heldout_ids":[r["id"] for r in test],
                "uncertainty":"tree disagreement plus a 0.05 log-space floor; empirical coverage reported, not calibrated guarantees",
                "numpy_version":np.__version__,"sklearn_version":sklearn.__version__,"random_seed":20261025,"trees":96,
                "normalized_records_sha256":hashlib.sha256(json.dumps(records,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
                "hash_scope":"canonical sorted JSON of normalized records; distinct from the source-file byte hash in benchmarks/audit.json",
                "evaluation":evaluation}
    (out/"surrogate_metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    return metadata


def run_experiments(records: Sequence[Mapping[str,Any]], output_dir: str | Path, *, budget_seconds: float | None = None,
                    seeds: Sequence[int] = tuple(range(5)), budgets: Budgets = Budgets(),
                    train_model_id: str = "banknote-4x8x2") -> dict[str,Any]:
    """Save trained model, heldout tests and repeated matched-compute replays."""
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Provide at least one distinct seed")
    out = Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    measured = [normalize_record(r) for r in records]
    train_surrogate(measured,out,train_model_id)
    # Search on training topology only. Other architectures stay outside search
    # and quantify surrogate generalization rather than expanding the pool.
    pool = [r for r in measured if r["model_id"] == train_model_id]
    if len(pool) < 4:
        raise ValueError("At least four measured designs are needed for replay comparisons")
    budget = budget_seconds if budget_seconds is not None else sum(r["compile_seconds"] for r in pool)*0.45
    runs = [replay(pool,budget_seconds=budget,strategy=strategy,seed=seed,budgets=budgets) for seed in seeds for strategy in STRATEGIES]
    reference = score(pool,budgets)
    summary = []
    for strategy in STRATEGIES:
        subset = [r for r in runs if r["strategy"] == strategy]
        values = np.asarray([r["hypervolume"] for r in subset])
        summary.append({"strategy":strategy,"seeds":len(subset),"hypervolume_mean":float(values.mean()),
                        "hypervolume_std":float(values.std(ddof=1)) if len(values)>1 else 0.,
                        "reference_hypervolume_fraction_mean":float(values.mean()/reference) if reference else None,
                        "completed_compile_seconds_mean":float(np.mean([r["completed_compile_seconds"] for r in subset])),
                        "acquisition_wall_seconds_mean":float(np.mean([r["acquisition_wall_seconds"] for r in subset])),
                        "routed_candidates_mean":float(np.mean([r["routed_candidates"] for r in subset]))})
    result = {"schema_version":1,"evaluation":"offline finite-pool measured-cost replay",
              "model_id":train_model_id,"candidate_count":len(pool),"budget_seconds":budget,"constraints":asdict(budgets),
              "reference_hypervolume":reference,"summary":summary,"runs":runs,
              "feasibility_sensitivity":[{"min_accuracy":a,"max_lut":budgets.max_lut,"max_latency_us":budgets.max_latency_us,
                                         "feasible_candidates":sum(objective_point(r,Budgets(a,budgets.max_lut,budgets.max_latency_us,budgets.clock_mhz)) is not None for r in pool),
                                         "total_candidates":len(pool)} for a in (.90,.98,1.0)],
              "limits":["One dataset, small dense networks and a finite premeasured candidate pool; not a broad superiority claim.",
                        "Compile costs are replayed measured durations. Search acquisition CPU cost is separately measured and not included in the matched FPGA-tool budget.",
                        "Accuracy and cycle counts are cheap known information; routed timing and synthesis resources are revealed only by a paid query.",
                        "Queries finishing beyond the budget are censored without revealing their labels or selecting a cheaper alternative.",
                        "Tree spread is approximate uncertainty; heldout empirical interval coverage can be poor."]}
    (out/"experiments.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


def optimize(model: Mapping[str,Any], configs: Sequence[Any], root: str | Path, output_dir: str | Path, *,
             budgets: Budgets = Budgets(), max_evaluations: int = 12, budget_seconds: float = 600., seed: int = 0,
             accuracy_fn: Any = None) -> dict[str,Any]:
    """Run the policy against real tools and account for every attempted stage.

    The default accuracy callback uses packaged validation data. An imported
    model can provide accuracy_fn(model, HardwareConfig)->validation fraction.
    A noninterruptible stage may overrun; no subsequent stage starts afterward.
    """
    from .compiler import compile_model
    from .dataset import evaluate_accuracy
    from .model import HardwareConfig, validate_model
    from .toolchain import run_build
    from .verification import verify_model
    import hashlib

    if max_evaluations < 1 or not math.isfinite(budget_seconds) or budget_seconds <= 0:
        raise ValueError("max_evaluations and budget_seconds must be positive")
    model = validate_model(model)
    out = Path(output_dir).resolve()
    out.mkdir(parents=True,exist_ok=True)
    root = Path(root).resolve()
    search_start = time.perf_counter()
    pool: list[dict[str,Any]] = []
    directories: dict[str,Path] = {}
    configuration: dict[str,HardwareConfig] = {}
    for c in configs:
        cfg = c if isinstance(c,HardwareConfig) else HardwareConfig.from_dict(c)
        ident = "live-"+hashlib.sha256(json.dumps(cfg.to_dict(),sort_keys=True).encode()).hexdigest()[:10]
        if ident in configuration:
            continue
        directory = out/ident
        manifest = compile_model(model,cfg,directory)
        accuracy = float(accuracy_fn(model,cfg)) if accuracy_fn else float(evaluate_accuracy(dict(model),cfg,root,split="validation")["accuracy"])
        if not 0 <= accuracy <= 1:
            raise ValueError("accuracy_fn must return a validation fraction in [0,1]")
        pool.append({"id":ident,"model_id":model["name"],"dimensions":manifest["dimensions"],"config":cfg.to_dict(),
                     "accuracy":accuracy,"latency_cycles":manifest["latency_cycles"]})
        configuration[ident] = cfg
        directories[ident] = directory
        if time.perf_counter()-search_start >= budget_seconds:
            break
    observations: dict[str,dict[str,Any]] = {}
    failures: list[dict[str,Any]] = []
    history: list[dict[str,Any]] = []
    verified: dict[str,dict[str,Any]] = {}
    failed_ids: set[str] = set()
    successful_compile_seconds = 0.0
    failed_tool_seconds = 0.0
    attempted_tool_seconds = 0.0
    total_verification = 0.0

    def save_result() -> dict[str,Any]:
        elapsed = time.perf_counter()-search_start
        completed = [r for r in observations.values() if r.get("routed")]
        result = {"schema_version":1,"evaluation":"live open-toolchain search","model_id":model["name"],"constraints":asdict(budgets),
                  "seed":seed,"max_evaluations":max_evaluations,"budget_seconds":budget_seconds,"candidate_pool":pool,
                  "elapsed_seconds":elapsed,"compile_seconds":successful_compile_seconds+failed_tool_seconds,
                  "successful_compile_seconds":successful_compile_seconds,"failed_tool_seconds":failed_tool_seconds,
                  "attempted_tool_seconds":attempted_tool_seconds,"verification_seconds":total_verification,
                  "candidates":list(observations.values()),"failures":failures,"history":history,
                  "verification_only_jobs":[r["id"] for r in observations.values() if r.get("verification_only")],
                  "budget_overrun_seconds":max(0.,elapsed-budget_seconds),"pareto_ids":pareto_front(completed,budgets),
                  "cost_scope":"compile_seconds = reported successful stage durations + actual wall time of failed tool attempts; attempted_tool_seconds includes all build-call overhead. Synthesis promotion is charged once."}
        temp = out/"live-search.json.tmp"
        temp.write_text(json.dumps(result,indent=2)+"\n")
        temp.replace(out/"live-search.json")
        return result

    for iteration in range(max_evaluations):
        wall_elapsed = time.perf_counter()-search_start
        if wall_elapsed >= budget_seconds:
            break
        query = propose([r for r in pool if r["id"] not in failed_ids],list(observations.values()),budgets=budgets,seed=seed)
        if query is None:
            break
        if query.get("predicted_cost_seconds",0.) > budget_seconds-wall_elapsed:
            break
        ident = str(query["candidate_id"])
        candidate = next(r for r in pool if r["id"] == ident)
        query_compile_seconds = 0.0
        stop_after_query = False
        try:
            if ident not in verified:
                started = time.perf_counter()
                try:
                    vectors = None
                    if accuracy_fn is None:
                        from .dataset import load_dataset
                        from .reference import quantize_input
                        values,_ = load_dataset(root,"validation")
                        vectors = [quantize_input(row,configuration[ident]) for row in values]
                    verification = verify_model(model,configuration[ident],directories[ident],vectors=vectors)
                    if verification.get("passed") is not True:
                        raise RuntimeError("Independent RTL verification did not pass")
                    verified[ident] = verification
                finally:
                    total_verification += time.perf_counter()-started
            remaining = budget_seconds-(time.perf_counter()-search_start)
            if remaining <= 0:
                # Verification may consume the remaining time. Preserve its
                # evidence without launching a new tool stage after the deadline.
                observations[ident] = dict(candidate,verified=True,routed=False,verification_only=True,
                                           artifacts=str(directories[ident].relative_to(out)))
                status = "verification_only_budget_exhausted"
                stop_after_query = True
            else:
                had_synthesis = ident in observations and "lut" in observations[ident]
                tool_start = time.perf_counter()
                try:
                    report = run_build(model,configuration[ident],directories[ident],route=query["fidelity"]=="route",
                                       clock_mhz=budgets.clock_mhz,reuse_synthesis=had_synthesis,time_budget_seconds=remaining)
                except (RuntimeError,ValueError,OSError):
                    failure_cost = time.perf_counter()-tool_start
                    failed_tool_seconds += failure_cost
                    query_compile_seconds += failure_cost
                    raise
                finally:
                    attempted_tool_seconds += time.perf_counter()-tool_start
                query_compile_seconds = float(report["route_seconds"]) if had_synthesis else float(report["compile_seconds"])
                successful_compile_seconds += query_compile_seconds
                if report["routed"] and (report.get("fmax_mhz") is None or report["fmax_mhz"] <= 0):
                    raise RuntimeError("Routing produced no usable clock-frequency estimate")
                revealed = dict(candidate,lut=report["lut"],ff=report["ff"],synthesis_seconds=report["synthesis_seconds"],
                                verified=True,routed=report["routed"],artifacts=str(directories[ident].relative_to(out)))
                if report["routed"]:
                    revealed.update(fmax_mhz=report["fmax_mhz"],route_seconds=report["route_seconds"],
                                    compile_seconds=report["compile_seconds"],dsp=report["dsp"],bram=report["bram"])
                observations[ident] = revealed
                status = "routed" if report["routed"] else "synthesized"
                if report.get("budget_exhausted_before_route"):
                    status = "synthesized_budget_exhausted_before_route"
                    stop_after_query = True
            completed = [r for r in observations.values() if r.get("routed")]
            history.append(dict(query,iteration=iteration+1,status=status,compile_seconds=query_compile_seconds,
                                elapsed_seconds=time.perf_counter()-search_start,hypervolume=score(completed,budgets),routed_candidates=len(completed)))
        except (RuntimeError,ValueError,OSError) as exc:
            failures.append({"candidate_id":ident,"fidelity":query["fidelity"],"error":str(exc),
                             "compile_seconds":query_compile_seconds,"artifacts":str(directories[ident].relative_to(out))})
            failed_ids.add(ident)
            completed = [r for r in observations.values() if r.get("routed")]
            history.append(dict(query,iteration=iteration+1,status="failed",compile_seconds=query_compile_seconds,
                                elapsed_seconds=time.perf_counter()-search_start,hypervolume=score(completed,budgets),routed_candidates=len(completed)))
        save_result()
        if stop_after_query:
            break
    return save_result()
