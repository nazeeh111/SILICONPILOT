"""Integer golden model. No HDL generation logic is shared with this module."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
from .model import HardwareConfig


def wrap(value: int, bits: int) -> int:
    value = int(value) % (1 << bits)
    return value - (1 << bits) if value >= (1 << (bits - 1)) else value


def saturate(value: int, bits: int) -> int:
    return max(-(1 << (bits - 1)), min((1 << (bits - 1)) - 1, int(value)))


def quantize_input(values: Sequence[float], config: HardwareConfig) -> list[int]:
    import math
    if any(not math.isfinite(float(v)) for v in values):
        raise ValueError('input values must be finite')
    return [saturate(round(float(v) * (1 << config.fractional_bits)), config.bits) for v in values]


def evaluate_integer(quantized: Mapping[str, Any], values: Sequence[int]) -> list[int]:
    cfg = HardwareConfig.from_dict(quantized['config'])
    if len(values) != quantized['input_size']:
        raise ValueError('input shape does not match model')
    if any(type(v) is not int or not -(1 << (cfg.bits-1)) <= v < (1 << (cfg.bits-1)) for v in values):
        raise ValueError('integer inputs must fit the signed activation width')
    activations = list(values)
    for layer in quantized['layers']:
        result = []
        for weights, bias in zip(layer['weights'], layer['bias']):
            total = wrap(int(bias) + sum(int(a) * int(w) for a, w in zip(activations, weights)), cfg.accumulator_bits)
            output = saturate(total >> cfg.fractional_bits, cfg.bits)
            result.append(max(0, output) if layer['relu'] else output)
        activations = result
    return activations


def evaluate_float(model: Mapping[str, Any], values: Sequence[float]) -> list[float]:
    if len(values) != model['input_size']:
        raise ValueError('input shape does not match model')
    activations = list(values)
    for layer in model['layers']:
        if layer['op'] == 'relu':
            activations = [max(0.0, v) for v in activations]
        else:
            activations = [sum(a*w for a,w in zip(activations,row)) + bias for row,bias in zip(layer['weights'],layer['bias'])]
    return activations
