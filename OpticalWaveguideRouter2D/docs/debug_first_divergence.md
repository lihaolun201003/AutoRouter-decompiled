# First divergence analysis — `below -> below` track selection

This note records the state evidence behind the conclusion in
[exact_legacy_fidelity_report.md](exact_legacy_fidelity_report.md): the
reconstruction's `wiring_rect_below` matches the original executable exactly,
and the only divergence is between the original executable and the **2020
figure** shipped next to it.

Method: `tools/legacy_runtime_trace.py` runs the original bytecode under
Python 3.8.10 / NumPy 1.18.5 / pandas 1.0.4 and records the internal state of
every accepted `below -> below` route with `sys.settrace`;
`tools/reconstruction_trace.py` records the same structure from the Python 3.10
reconstruction. Both key on the dataframe label, which is unambiguous because
`create_sim_space` reproduces the legacy snapshot exactly (including the row
order).

---

## 1. Baseline before this hotfix

Reference: `AutoRouter\fiberBoard512_rect.pdf` (2020).

```
overall       exact=266/512   +1=235   -1=0   other=11
below->below  exact= 39/112   +1= 62   other=11
above->above  exact=112/112
below->above  exact=115/115
above->below  exact=  0/173   +1=173
```

Suspected root: the `below -> below` pass, with `above -> below` inheriting the
offset through `below_line = max(df2["inflection"])`.

---

## 2. First divergence found — and it is not in the reconstruction

Running both implementations and diffing their state route by route:

```
routes:                        legacy=112   reconstruction=112
processing-order label sequence: identical
ports / idx1 / idx2:             identical
sx / lx max difference:          0 / 0
routes with a different track:   0 / 112
nodes.MTbelow snapshots:         max delta 0
```

**There is no divergence between the original program and the reconstruction.**
Every route ordinal, including the ones the 2020 figure disagrees about, is
identical.

The first divergence that does exist is between the **2020 figure** and the
original program. Its per-route ordinal cannot be reported, because the figure's
port fan-out order is itself derived from its own track choices, so it is only
comparable as a multiset:

```
2020 figure vs the original program (and vs the reconstruction)
  below->below  39/112 exact, 62 off by +1 track, 11 more
  above->above  112/112 exact
  below->above  115/115 exact
  above->below  0/173 exact, all off by +1 track
```

Concretely, for the track the 2020 build raised by one step, the original
program (and therefore the reconstruction) accepts the lower track because
**no rejection condition fires**: at that moment the neighbouring tracks the
scan inspects — three behind the candidate and seven ahead of it — carry no
waveguides at all, so `noCross` returns `True` under every reading of its
conditions.

---

## 3. State at the divergence point

Original program and reconstruction, identical at every route; the values below
are from the traced state of the route the 2020 figure disagrees about
(`Port1=73`, `Port2=70`, `idx1=27`, `idx2=19`, `sx=123.500`, `lx=89.775`):

```
candidate scan for that route
  i=134  y=28.450   rejected: backward scan j=3 -> track 131
                    WGs=[75], rEnd=[-1, 26], lEnd=[100, 2]
                    A: i>=j and WGs and rEnd[-1]=26 < rEnd=27 and lEnd[-1]=2 < lEnd=19  -> TRUE
  i=135  y=28.625   accepted
                    backward j=1..3 -> tracks 134, 133, 132: WGs empty
                    forward  J=1..7 -> tracks 136..142: WGs empty
                    ln_calc=7  sn_calc(idx2+1=20, y=28.625)=6  bound=max(7-6,4)=4
  chosen track 28.625 (track index 135)
2020 figure: 28.800
```

Both implementations agree on `ln_calc`, `sn_calc`, the loop bound, the four
`rEnd`/`lEnd` guards and the seven forward guards; the rejection traces are
byte-for-byte the same lists.

---

## 4. `nodes.MTbelow` bookkeeping

The slot update

```python
nodes.MTbelow[idx1].y[nodes.MTbelow[idx1].x.index(row[1]["sx"])] = w.y
nodes.MTbelow[idx2].y[nodes.MTbelow[idx2].x.index(row[1]["lx"])] = w.y
```

was traced in full — `x` contents and order, the matched slot, the previous
value and the new value — for all 112 routes. `x` is a sorted list of the
sixteen unique endpoint x positions of the port, so `list.index` resolves to a
unique slot, and the resulting `MTbelow` arrays are **identical** between the
two runs after every single route (max delta 0 over 112 snapshots × 32 ports ×
16 slots). This was the strongest single suspicion going in — float equality,
duplicate entries, or a differently ordered `x` list — and it is ruled out.

---

## 5. Where the 2020 figure's difference is localised

| Pass | `sn_calc` branch | 2020 figure vs original |
| --- | --- | --- |
| `above->above` | `isBelow=False` (reads `MTabove`) | identical |
| `below->above` | `isBelow=False` | identical |
| `below->below` | `isBelow=True` (reads `MTbelow`) | differs |
| `above->below` | reads `MTbelow` through `below_line` | uniform +1, inherited |

So the 2020 build differs only in the `MTbelow`-based bound of `noCross`; the
`above->below` block is entirely explained by the resulting
`below_line = max(df2["inflection"])` shift. A controlled experiment that
removed the `sn_calc` term from the bound (a plausible earlier form) reproduced
only 43/512 of the 2020 figure, so that is not what the older build did, and no
further guess is offered: the executable being reproduced is the one that was
decompiled, and the reconstruction matches *it* exactly.

---

## 6. Conclusion

```
First divergence between the reconstruction and the original executable: none
  (112/112 below->below routes, identical state after every route)

First divergence between the original executable and the 2020 figure:
  AutoRouter\fiberBoard512_rect.pdf — a different build of the same program
  below->below: 62 of 112 routes one track lower in the current build
  above->below: all 173 routes one track lower as a consequence
```

No code change was made. Tuning any of this to match the 2020 figure would
break fidelity with the executable the project reproduces.
