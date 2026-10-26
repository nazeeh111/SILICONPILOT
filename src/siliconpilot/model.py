"""Validated, deliberately small model interchange format."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

@dataclass(frozen=True)
class HardwareConfig:
    bits: int = 8
    fractional_bits: int = 5
    accumulator_bits: int = 24
    parallelism: int = 1
    pipeline: bool = False
    buffering: int = 1

    def __post_init__(self) -> None:
        for key in ('bits', 'fractional_bits', 'accumulator_bits', 'parallelism', 'buffering'):
            if type(getattr(self, key)) is not int:
                raise ValueError(f'{key} must be an integer')
        if not 3 <= self.bits <= 16:
            raise ValueError('bits must be between 3 and 16')
        if not 0 <= self.fractional_bits < self.bits:
            raise ValueError('fractional_bits must be in [0, bits)')
        if not 2 * self.bits <= self.accumulator_bits <= 48:
            raise ValueError('accumulator_bits must be in [2*bits, 48]')
        if not 1 <= self.parallelism <= 32:
            raise ValueError('parallelism must be in [1, 32]')
        if self.buffering not in (1, 2):
            raise ValueError('buffering must be 1 or 2')
        if type(self.pipeline) is not bool:
            raise ValueError('pipeline must be boolean')

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> HardwareConfig:
        return cls(**dict(value))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_model(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError('model must be an object')
    unknown = set(value) - {'name', 'input_size', 'layers', 'metadata'}
    if unknown:
        raise ValueError(f'unsupported model fields: {sorted(unknown)}')
    size = value.get('input_size')
    if type(size) is not int or not 1 <= size <= 256:
        raise ValueError('input_size must be an integer in [1, 256]')
    layers = value.get('layers')
    if not isinstance(layers, list) or not 1 <= len(layers) <= 16:
        raise ValueError('layers must contain 1 to 16 dense/relu operations')
    dense_count = 0
    normalized: list[dict[str, Any]] = []
    for index, layer in enumerate(layers):
        if not isinstance(layer, Mapping):
            raise ValueError(f'layer {index} must be an object')
        op = layer.get('op')
        if op == 'relu':
            if set(layer) != {'op'} or not normalized or normalized[-1]['op'] != 'dense':
                raise ValueError('relu must immediately follow dense and has no attributes')
            normalized.append({'op': 'relu'})
            continue
        if op != 'dense':
            raise ValueError(f'unsupported operation {op!r}; supported: dense, relu')
        if set(layer) != {'op', 'weights', 'bias'}:
            raise ValueError('dense requires exactly op, weights, bias')
        weights, bias = layer['weights'], layer['bias']
        if not isinstance(weights, list) or not 1 <= len(weights) <= 256:
            raise ValueError('dense output dimension must be in [1, 256]')
        if not isinstance(bias, list) or len(bias) != len(weights):
            raise ValueError('bias dimension must equal output dimension')
        if any(not isinstance(row, list) or len(row) != size for row in weights):
            raise ValueError(f'layer {index} requires weight rows of length {size}')
        numbers = [v for row in weights for v in row] + bias
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in numbers):
            raise ValueError('all parameters must be finite real numbers')
        normalized.append({'op': 'dense', 'weights': [[float(v) for v in row] for row in weights], 'bias': [float(v) for v in bias]})
        size = len(weights)
        dense_count += 1
    if dense_count == 0:
        raise ValueError('at least one dense layer is required')
    return {'name': str(value.get('name', 'network')), 'input_size': value['input_size'], 'layers': normalized, 'metadata': value.get('metadata', {})}


def load_model(path: str | Path) -> dict[str, Any]:
    return validate_model(json.loads(Path(path).read_text()))


def quantize(model: Mapping[str, Any], config: HardwareConfig) -> dict[str, Any]:
    from .reference import saturate, wrap
    model = validate_model(model)
    scale = 1 << config.fractional_bits
    layers: list[dict[str, Any]] = []
    for layer in model['layers']:
        if layer['op'] == 'relu':
            layers[-1]['relu'] = True
        else:
            layers.append({'weights': [[saturate(round(v * scale), config.bits) for v in row] for row in layer['weights']], 'bias': [wrap(round(v * scale * scale), config.accumulator_bits) for v in layer['bias']], 'relu': False})
    return {'name': model['name'], 'input_size': model['input_size'], 'layers': layers, 'config': config.to_dict()}
