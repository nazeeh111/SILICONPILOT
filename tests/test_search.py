"""Deterministic mathematical/search contracts; toy measurements are test-only."""
from copy import deepcopy
import pytest
from siliconpilot.search import Budgets, CostSurrogate, features, hypervolume, normalize_record, pareto_front, propose, public_candidate, replay, score


def corpus():
    return [{"id":f"test{i}","model_id":"test","dimensions":[4,8,2],
             "config":{"bits":8,"fractional_bits":5,"accumulator_bits":24,"parallelism":i+1,"pipeline":False,"buffering":1},
             "accuracy":.96+i*.001,"latency_cycles":100-i*10,"lut":200+i*80,"ff":100+i*10,
             "fmax_mhz":50.,"synthesis_seconds":2.,"route_seconds":3.,"verified":True,"routed":True}
            for i in range(6)]


def test_exact_hypervolume_union():
    assert hypervolume([(0.,0.,0.)]) == 1.
    assert hypervolume([(.5,.5,.5)]) == pytest.approx(.125)
    assert hypervolume([(.5,.5,.5),(.5,.5,.5)]) == pytest.approx(.125)
    assert hypervolume([(.25,.75,.5),(.75,.25,.5)]) == pytest.approx(.15625)
    assert hypervolume([(1,0,0),(2,0,0)]) == 0


def test_features_cannot_read_unrevealed_measurements():
    record = corpus()[0]
    assert features(public_candidate(record)) == features(record)
    assert len(features(record)) == 13


def test_replay_budget_and_two_fidelities():
    records = corpus()
    run = replay(records,budget_seconds=17.,strategy="cost_aware",seed=1)
    assert run["completed_compile_seconds"] <=17.
    assert all(h["elapsed_seconds"] <=17. for h in run["history"])
    assert run["censored_query"]["would_finish_at_seconds"] >17.
    assert all(h["fidelity"] in ("route","synthesis") for h in run["history"])
    assert [h["hypervolume"] for h in run["history"]] == sorted(h["hypervolume"] for h in run["history"])


def test_replay_deterministic_selections():
    a = replay(corpus(),budget_seconds=20.,strategy="random",seed=3)
    b = replay(corpus(),budget_seconds=20.,strategy="random",seed=3)
    assert [h["candidate_id"] for h in a["history"]] == [h["candidate_id"] for h in b["history"]]
    assert a["hypervolume"] == b["hypervolume"]


def test_no_test_accuracy_leak():
    records = corpus()
    records[0]["accuracy_split"] = "test"
    with pytest.raises(ValueError,match="never test"):
        normalize_record(records[0])


def test_reject_unmeasured_and_unverified():
    record=corpus()[0]
    record["routed"]=False
    with pytest.raises(ValueError,match="successfully routed"):
        normalize_record(record)
    del record["lut"]
    with pytest.raises(ValueError,match="measured lut"):
        normalize_record(record)


def test_budget_constraints_change_feasible_designs():
    records = corpus()
    assert score(records,Budgets(max_lut=3000)) > score(records,Budgets(max_lut=100))
    assert score(records,Budgets(clock_mhz=100)) == 0 # target timing is not met
    assert pareto_front(records,Budgets(max_lut=100)) == []


def test_proposal_only_uses_revealed_observations():
    records=corpus()
    pool=[public_candidate(r) for r in records]
    seen=[normalize_record(r) for r in records[:3]]
    a=propose(pool,seen,seed=7)
    modified=deepcopy(records)
    for r in modified[3:]:
        r["lut"]*=100
        r["fmax_mhz"]=.01
        r["synthesis_seconds"]*=100
    b=propose([public_candidate(r) for r in modified],seen,seed=7)
    assert a==b


def test_partial_synthesis_does_not_train_timing():
    records=corpus()
    partial=[dict(public_candidate(r),lut=r["lut"],synthesis_seconds=r["synthesis_seconds"]) for r in records]
    model=CostSurrogate(trees=8).fit(partial)
    assert model.train_counts["lut"]==6
    assert model.train_counts["fmax_mhz"]==0
    assert model.predict_log([public_candidate(records[0])]).shape==(1,16,4)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        Budgets(min_accuracy=1.1)
    with pytest.raises(ValueError,match="positive"):
        replay(corpus(),budget_seconds=0,strategy="random")
    with pytest.raises(ValueError,match="Unknown"):
        propose([public_candidate(corpus()[0])],[],strategy="fake")


def test_gp_ehvi_produces_a_full_route_query():
    records=corpus()
    query=propose([public_candidate(r) for r in records],records[:3],strategy="gp_ehvi",seed=2)
    assert query["candidate_id"] in {r["id"] for r in records[3:]}
    assert query["fidelity"]=="route"
    assert query["acquisition"]>=0


def test_live_optimize_uses_actual_backend_and_saves_failures(monkeypatch,tmp_path):
    from siliconpilot.search import optimize
    import siliconpilot.toolchain as backend
    import siliconpilot.verification as verifier
    from siliconpilot.model import HardwareConfig
    model={"name":"custom","input_size":1,"layers":[{"op":"dense","weights":[[.5]],"bias":[0.]}]}
    calls=[]
    def verify(*args,**kwargs):
        return {"passed":True}
    def build(model,config,directory,route=True,clock_mhz=25.,reuse_synthesis=False,time_budget_seconds=None):
        calls.append((route,reuse_synthesis))
        if config.parallelism==2:
            raise RuntimeError("deliberate backend failure")
        return {"lut":100,"ff":50,"synthesis_seconds":.1,"route_seconds":.2 if route else 0.,
                "compile_seconds":.3 if route else .1,"routed":route,"fmax_mhz":50.,"dsp":0,"bram":0}
    monkeypatch.setattr(verifier,"verify_model",verify)
    monkeypatch.setattr(backend,"run_build",build)
    result=optimize(model,[HardwareConfig(parallelism=1),HardwareConfig(parallelism=2)],tmp_path,tmp_path/"run",
                    max_evaluations=2,budget_seconds=60.,accuracy_fn=lambda model,cfg:.99)
    assert len(calls)==2
    assert len(result["candidates"])==1
    assert len(result["failures"])==1
    assert result["successful_compile_seconds"]==pytest.approx(.3)
    assert result["compile_seconds"]>=.3
    assert result["failed_tool_seconds"]>=0
    assert (tmp_path/"run/live-search.json").is_file()
    assert result["candidates"][0]["verified"] is True


def test_fixed_architectures_keep_lane_count():
    records=corpus()
    pool=[public_candidate(r) for r in records]
    serial=propose(pool,[],strategy="fixed_serial")
    parallel=propose(pool,[],strategy="fixed_parallel")
    assert serial["candidate_id"]==records[0]["id"]
    assert parallel["candidate_id"]==records[-1]["id"]
    assert propose(pool,[records[0]],strategy="fixed_serial") is None


def test_live_promotion_reuses_synthesis_and_charges_once(monkeypatch,tmp_path):
    import siliconpilot.search as search
    import siliconpilot.toolchain as backend
    import siliconpilot.verification as verifier
    from siliconpilot.model import HardwareConfig
    model={"name":"custom","input_size":1,"layers":[{"op":"dense","weights":[[.5]],"bias":[0.]}]}
    calls=[]
    def policy(pool,observations,**kwargs):
        return {"candidate_id":pool[0]["id"],"fidelity":"synthesis" if not observations else "route","acquisition":1.}
    def build(model,config,directory,route=True,clock_mhz=25.,reuse_synthesis=False,time_budget_seconds=None):
        calls.append((route,reuse_synthesis))
        return {"lut":100,"ff":50,"synthesis_seconds":.1,"route_seconds":.2 if route else 0.,
                "compile_seconds":.3 if route else .1,"routed":route,"fmax_mhz":50.,"dsp":0,"bram":0}
    monkeypatch.setattr(search,"propose",policy)
    monkeypatch.setattr(verifier,"verify_model",lambda *args,**kwargs:{"passed":True})
    monkeypatch.setattr(backend,"run_build",build)
    result=search.optimize(model,[HardwareConfig()],tmp_path,tmp_path/"run",max_evaluations=2,budget_seconds=60.,accuracy_fn=lambda *args:.99)
    assert calls==[(False,False),(True,True)]
    assert result["compile_seconds"]==pytest.approx(.3)
    assert len(result["candidates"])==1
    assert result["candidates"][0]["routed"] is True


def test_verification_deadline_prevents_any_build(monkeypatch,tmp_path):
    import siliconpilot.search as search
    import siliconpilot.toolchain as backend
    import siliconpilot.verification as verifier
    from siliconpilot.model import HardwareConfig
    model={"name":"custom","input_size":1,"layers":[{"op":"dense","weights":[[.5]],"bias":[0.]}]}
    clock={"now":0.}
    monkeypatch.setattr(search.time,"perf_counter",lambda:clock["now"])
    def verify(*args,**kwargs):
        clock["now"]=2.
        return {"passed":True}
    def forbidden(*args,**kwargs):
        pytest.fail("No synthesis may start after verification exhausts the budget")
    monkeypatch.setattr(verifier,"verify_model",verify)
    monkeypatch.setattr(backend,"run_build",forbidden)
    result=search.optimize(model,[HardwareConfig()],tmp_path,tmp_path/"run",max_evaluations=2,budget_seconds=1.,accuracy_fn=lambda *args:.99)
    assert result["compile_seconds"]==0.
    assert result["verification_seconds"]==2.
    assert result["budget_overrun_seconds"]==1.
    assert len(result["verification_only_jobs"])==1
    assert result["history"][0]["status"]=="verification_only_budget_exhausted"
    assert (tmp_path/"run/live-search.json").is_file()


def test_failed_build_attempt_time_is_charged(monkeypatch,tmp_path):
    import siliconpilot.search as search
    import siliconpilot.toolchain as backend
    import siliconpilot.verification as verifier
    from siliconpilot.model import HardwareConfig
    model={"name":"custom","input_size":1,"layers":[{"op":"dense","weights":[[.5]],"bias":[0.]}]}
    clock={"now":0.}
    monkeypatch.setattr(search.time,"perf_counter",lambda:clock["now"])
    monkeypatch.setattr(verifier,"verify_model",lambda *args,**kwargs:{"passed":True})
    def fail(*args,**kwargs):
        clock["now"]+=3.25
        raise RuntimeError("deliberate tool failure after consuming time")
    monkeypatch.setattr(backend,"run_build",fail)
    result=search.optimize(model,[HardwareConfig()],tmp_path,tmp_path/"run",max_evaluations=1,budget_seconds=60.,accuracy_fn=lambda *args:.99)
    assert result["compile_seconds"]==3.25
    assert result["successful_compile_seconds"]==0.
    assert result["failed_tool_seconds"]==3.25
    assert result["attempted_tool_seconds"]==3.25
    assert result["history"][0]["compile_seconds"]==3.25
    assert result["failures"][0]["compile_seconds"]==3.25


def test_route_skipped_by_backend_is_reported_as_synthesis_only(monkeypatch,tmp_path):
    import siliconpilot.search as search
    import siliconpilot.toolchain as backend
    import siliconpilot.verification as verifier
    from siliconpilot.model import HardwareConfig
    model={"name":"custom","input_size":1,"layers":[{"op":"dense","weights":[[.5]],"bias":[0.]}]}
    calls=[]
    monkeypatch.setattr(verifier,"verify_model",lambda *args,**kwargs:{"passed":True})
    def build(*args,**kwargs):
        calls.append(kwargs)
        return {"lut":100,"ff":50,"synthesis_seconds":.1,"route_seconds":0.,"compile_seconds":.1,
                "routed":False,"budget_exhausted_before_route":True}
    monkeypatch.setattr(backend,"run_build",build)
    result=search.optimize(model,[HardwareConfig()],tmp_path,tmp_path/"run",max_evaluations=3,budget_seconds=60.,accuracy_fn=lambda *args:.99)
    assert len(calls)==1
    assert calls[0]["time_budget_seconds"]>0
    assert result["candidates"][0]["routed"] is False
    assert result["history"][0]["status"]=="synthesized_budget_exhausted_before_route"


def test_every_policy_filters_known_infeasible_latency():
    from siliconpilot.search import STRATEGIES
    pool=[public_candidate(r) for r in corpus()]
    for strategy in STRATEGIES:
        query=propose(pool,[],strategy=strategy,budgets=Budgets(max_latency_us=2.1))
        # Fixed serial has no member meeting the latency bound. Every other
        # selected query must be the only candidate whose analytic latency fits.
        assert query is None or query["candidate_id"]==pool[-1]["id"]
        assert propose(pool,[],strategy=strategy,budgets=Budgets(max_latency_us=1.)) is None
