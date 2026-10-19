"""Execute the two original nested track rules without rewriting their bodies.

Only the surrounding data adapts to the four-side, 32-channel connectors.
``sn_calc`` and ``noCross`` are extracted as AST nodes from the unchanged
``wiring_rect_826.plotter_rect``. The caller supplies the new coordinate/channel
``ln_calc`` adapter and performs the original first-free-track scan. There is
no candidate search, route optimization, or change to the legacy rule bodies.
"""
from __future__ import annotations

import ast
import copy
from functools import lru_cache
import hashlib
import math
from pathlib import Path

from wiring_rect_826 import MT, MTset, WGyset

LEGACY_SOURCE = Path(__file__).resolve().parents[1] / 'wiring_rect_826.py'
CHANNELS_PER_CONNECTOR = 32
RULE_NAMES = ('sn_calc', 'noCross')

__all__ = ['LegacyRules', 'nodesMTset', 'channel_ln_calc', 'WGyset',
           'MT', 'MTset', 'source_provenance', 'extracted_rule_ast']


@lru_cache(maxsize=1)
def _extracted():
    raw = LEGACY_SOURCE.read_bytes()
    source = raw.decode('utf-8-sig')
    tree = ast.parse(source, filename=str(LEGACY_SOURCE))
    plotter = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == 'plotter_rect')
    rules = {node.name: node for node in plotter.body
             if isinstance(node, ast.FunctionDef) and node.name in RULE_NAMES}
    if set(rules) != set(RULE_NAMES):
        raise RuntimeError('Cannot locate original plotter_rect.sn_calc/noCross')
    # Hashes omit line/column positions; the source-byte hash additionally pins
    # the exact legacy file, including text and decompilation repairs.
    details = {}
    for name in RULE_NAMES:
        node = rules[name]
        segment = ast.get_source_segment(source, node)
        details[name] = dict(
            qualified_name='wiring_rect_826.plotter_rect.' + name,
            lineno=node.lineno, end_lineno=node.end_lineno,
            source_segment_sha256=hashlib.sha256(segment.encode('utf-8')).hexdigest(),
            ast_sha256=hashlib.sha256(ast.dump(node, include_attributes=False).encode('utf-8')).hexdigest(),
            body_ast_sha256=hashlib.sha256(ast.dump(ast.Module(body=node.body,type_ignores=[]),
                include_attributes=False).encode('utf-8')).hexdigest())
    provenance = dict(
        source_file=str(LEGACY_SOURCE), source_file_sha256=hashlib.sha256(raw).hexdigest(),
        extraction='Direct nested FunctionDef AST extraction; function bodies unchanged',
        rules=details, original_WGyset='wiring_rect_826.WGyset',
        adapted_surroundings=['32-channel MT coordinate/track state',
                              'caller supplied ln_calc coordinate/channel callback',
                              'caller supplied four-side coordinate frame and track scan'],
        unchanged_legacy_constants=dict(sn_calc_fallback=8),
        limitation='Rule bodies retain their original two-side track semantics. Four-side transforms and global geometry checking are the caller responsibility.')
    return rules, provenance


def extracted_rule_ast(name):
    """A defensive copy, allowing tests to compare the actual extracted AST."""
    if name not in RULE_NAMES:
        raise KeyError(name)
    return copy.deepcopy(_extracted()[0][name])


def source_provenance():
    return copy.deepcopy(_extracted()[1])


def nodesMTset(above, below, height=150.):
    """Build the original MTset with all 32 channels in each connector.

    ``above``/``below`` are equally sized sequences of connectors. Each entry
    contains the 32 fixed port x coordinates in the caller's local frame.
    Their ascending order and the initial track values exactly follow the
    original init_MT_set, except that every connector now has 32 channels.
    These y entries are routing-track state, not additional routing layers.
    """
    if not math.isfinite(height) or height <= 0:
        raise ValueError('height must be positive and finite')
    above, below = list(above), list(below)
    if len(above) != len(below):
        raise ValueError('Legacy sn_calc requires equal above/below connector counts')

    def build(entries, initial_y):
        result = []
        for coordinates in entries:
            xs = sorted(map(float, coordinates))
            if len(xs) != CHANNELS_PER_CONNECTOR:
                raise ValueError('Each MT connector must contain all 32 channels')
            if not all(math.isfinite(x) for x in xs) or len(set(xs)) != len(xs):
                raise ValueError('Connector channel coordinates must be finite and unique')
            result.append(MT(x=xs, y=[float(initial_y)] * CHANNELS_PER_CONNECTOR))
        return result

    return MTset(MTabove=build(above, 0.), MTbelow=build(below, height))


def channel_ln_calc(endpoint_channels, *, minimum=4, legacy_offset=6, coordinate_digits=9):
    """Adapt the original fanout-order quantity to explicit 1..32 channels.

    ``endpoint_channels`` maps fixed local ``(x,y)`` poses to the channel
    ordinal along the local x order. Unlike the original modulo connector
    pitch expression, this adapter never infers N or changes coordinates.
    The original expression was max(zero_based_channel - 6, 4); that arithmetic
    is kept. A reflected local frame must supply its own local channel ordinal
    (or the caller can pass any explicit ln_calc callback to LegacyRules).
    """
    lookup = {}
    for coordinate, channel in endpoint_channels.items():
        key = tuple(round(float(v), coordinate_digits) for v in coordinate)
        if len(key) != 2 or not all(math.isfinite(v) for v in key):
            raise ValueError('ln_calc requires finite 2D local endpoint coordinates')
        if isinstance(channel, bool) or int(channel) != channel or not 1 <= int(channel) <= CHANNELS_PER_CONNECTOR:
            raise ValueError('Channel must be an integer in 1..32')
        if key in lookup and lookup[key] != int(channel):
            raise ValueError('Conflicting channels at the same local endpoint coordinate')
        lookup[key] = int(channel)

    def ln_calc(lx, ly):
        key = round(float(lx), coordinate_digits), round(float(ly), coordinate_digits)
        if key not in lookup:
            raise KeyError(f'No fixed channel metadata for local endpoint {key}')
        return max(lookup[key] - 1 - legacy_offset, minimum)

    ln_calc.channel_lookup = dict(lookup)
    ln_calc.adapter_provenance = dict(source='explicit local 1..32 channel ordinals',
        formula='max(channel - 1 - legacy_offset, minimum)', legacy_offset=legacy_offset,
        minimum=minimum, coordinate_digits=coordinate_digits)
    return ln_calc


class LegacyRules:
    """Bind unchanged original rules to a four-side adapter's local MT state."""
    def __init__(self, nodes, ln_calc, r=5., height=150.):
        if not callable(ln_calc):
            raise TypeError('ln_calc must be a coordinate/channel callback')
        if not math.isfinite(r) or r <= 0 or not math.isfinite(height) or height <= 0:
            raise ValueError('r and height must be positive finite values')
        if len(nodes.MTabove) != len(nodes.MTbelow):
            raise ValueError('Legacy sn_calc requires equal above/below connector counts')
        for node in list(nodes.MTabove) + list(nodes.MTbelow):
            if len(node.x) != CHANNELS_PER_CONNECTOR or len(node.y) != CHANNELS_PER_CONNECTOR:
                raise ValueError('Legacy four-side adapter requires every MT to have 32 channels')
        self.nodes, self.r, self.height = nodes, float(r), float(height)
        self.ln_calc = ln_calc
        self.namespace = dict(nodes=nodes, ln_calc=ln_calc, r=self.r, height=self.height)
        module = ast.Module(body=[extracted_rule_ast(name) for name in RULE_NAMES], type_ignores=[])
        # No AST rewriting: defaults, loops, comparisons and all function bodies
        # are the exact nested definitions in the old source.
        exec(compile(module, str(LEGACY_SOURCE), 'exec'), self.namespace)
        self.sn_calc = self.namespace['sn_calc']
        self.noCross = self.namespace['noCross']
        self.provenance = source_provenance()
        self.provenance.update(channels_per_connector=CHANNELS_PER_CONNECTOR,
                               r_mm=self.r, height_mm=self.height)
