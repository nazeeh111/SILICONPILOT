"""Contract, arithmetic and real RTL regression tests."""
import json
import shutil
from pathlib import Path
import pytest
from siliconpilot.model import HardwareConfig, load_model, quantize, validate_model
from siliconpilot.reference import evaluate_float, evaluate_integer, quantize_input, saturate, wrap
from siliconpilot.compiler import compile_model
from siliconpilot.verification import verify_model


def model():
    return {'name':'test-network','input_size':3,'layers':[
        {'op':'dense','weights':[[.5,-.25,1.],[1.,1.,-1.]],'bias':[0.,.25]},
        {'op':'relu'},
        {'op':'dense','weights':[[1.,.5],[-1.,.25]],'bias':[.125,-.125]}]}


def test_known_integer_arithmetic():
    c=HardwareConfig(bits=4,fractional_bits=2,accumulator_bits=8)
    q=quantize({'input_size':4,'layers':[{'op':'dense','weights':[[1.75]*4],'bias':[0.]}]},c)
    # 4*7*7=196 wraps to -60 in signed 8 bits; floor(-60/4)=-15 saturates to -8.
    assert evaluate_integer(q,[7]*4)==[-8]
    assert wrap(128,8)==-128
    assert wrap(-129,8)==127
    assert saturate(128,8)==127
    assert saturate(-129,8)==-128


def test_ties_even_inputs_and_floor_requantization():
    c=HardwareConfig(bits=4,fractional_bits=2,accumulator_bits=8)
    assert quantize_input([.125,.375,-.125,-.375,100.,-100.],c)==[0,2,0,-2,7,-8]
    q=quantize({'input_size':1,'layers':[{'op':'dense','weights':[[.25]],'bias':[0.]}]},c)
    assert evaluate_integer(q,[-1])==[-1]  # arithmetic shift rounds toward minus infinity


def test_relu_and_dense_float_reference():
    m=model()
    assert evaluate_float(m,[0.,0.,0.])==[.25,-.0625]
    q=quantize(m,HardwareConfig())
    assert evaluate_integer(q,[0,0,0])==[8,-2]


@pytest.mark.parametrize('bad',[
    {'input_size':1,'layers':[{'op':'conv1d'}]},
    {'input_size':1,'layers':[{'op':'relu'}]},
    {'input_size':1,'layers':[{'op':'dense','weights':[[1.,2.]],'bias':[0.]}]},
    {'input_size':1,'layers':[{'op':'dense','weights':[[float('nan')]],'bias':[0.]}]},
    {'input_size':1,'layers':[{'op':'dense','weights':[[1.]],'bias':[0.],'activation':'sigmoid'}]},
    {'input_size':True,'layers':[{'op':'dense','weights':[[1.]],'bias':[0.]}]},
])
def test_reject_unsupported_or_malformed_models(bad):
    with pytest.raises(ValueError): validate_model(bad)


@pytest.mark.parametrize('kwargs',[{'bits':2},{'fractional_bits':8},{'accumulator_bits':15},{'parallelism':0},{'buffering':3},{'pipeline':1},{'bits':8.0}])
def test_config_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError): HardwareConfig(**kwargs)


def test_serialization_and_deterministic_generation(tmp_path):
    c=HardwareConfig.from_dict({'bits':8,'parallelism':2})
    p=tmp_path/'model.json';p.write_text(json.dumps(model()))
    m=load_model(p)
    a=compile_model(m,c,tmp_path/'a')
    b=compile_model(m,c,tmp_path/'b')
    assert a==b
    assert (tmp_path/'a'/'design.v').read_bytes()==(tmp_path/'b'/'design.v').read_bytes()
    assert a['latency_cycles']==7
    assert a['initiation_interval_cycles']==6


def test_reject_bad_input_shape_and_range():
    q=quantize(model(),HardwareConfig())
    with pytest.raises(ValueError): evaluate_integer(q,[0,0])
    with pytest.raises(ValueError): evaluate_integer(q,[0,0,128])
    with pytest.raises(ValueError): quantize_input([float('nan')],HardwareConfig())


@pytest.mark.skipif(not shutil.which('iverilog') or not shutil.which('vvp'), reason='Icarus Verilog is required for RTL simulation')
@pytest.mark.parametrize('pipeline,buffering,parallelism,bits',[
    (False,1,1,8),(False,1,2,8),(False,2,3,8),(True,1,2,8),(True,2,2,8),(False,1,5,4),(True,2,3,3),(True,1,2,16),
])
def test_generated_rtl_matches_independent_reference(tmp_path,pipeline,buffering,parallelism,bits):
    c=HardwareConfig(bits=bits,fractional_bits=min(3,bits-1),accumulator_bits=2*bits,parallelism=parallelism,pipeline=pipeline,buffering=buffering)
    report=verify_model(model(),c,tmp_path,random_count=50)
    assert report['passed']
    assert report['results']['core']['backpressure_cycles']>0
    assert report['results']['streaming']['backpressure_cycles']>0
    assert report['results']['core']['reset_assertion_checks']>=7
    assert report['results']['streaming']['reset_assertion_checks']>=7
    assert report['samples']==62


@pytest.mark.skipif(not shutil.which('iverilog') or not shutil.which('vvp'), reason='Icarus Verilog is required for RTL simulation')
def test_overflow_and_saturation_in_generated_rtl(tmp_path):
    c=HardwareConfig(bits=4,fractional_bits=2,accumulator_bits=8,parallelism=3,pipeline=True,buffering=2)
    m={'input_size':4,'layers':[{'op':'dense','weights':[[1.75]*4,[-1.75]*4],'bias':[0.,1.]}]}
    report=verify_model(m,c,tmp_path,[[7]*4,[-8]*4],random_count=32)
    assert report['passed']


@pytest.mark.skipif(not shutil.which('iverilog') or not shutil.which('vvp'), reason='Icarus Verilog is required for RTL simulation')
def test_three_stages_with_final_relu(tmp_path):
    m=model()
    m['layers'].extend([{'op':'relu'},{'op':'dense','weights':[[.75,-1.25]],'bias':[-.125]},{'op':'relu'}])
    c=HardwareConfig(bits=5,fractional_bits=2,accumulator_bits=10,parallelism=3,pipeline=True,buffering=2)
    assert verify_model(m,c,tmp_path,random_count=48)['passed']


@pytest.mark.skipif(not shutil.which('yosys'), reason='Yosys is required for bounded formal proof')
def test_tiny_formal_proof(tmp_path):
    from siliconpilot.formal import prove_tiny
    report=prove_tiny(tmp_path)
    assert report['passed']
    assert report['input_combinations']==64
