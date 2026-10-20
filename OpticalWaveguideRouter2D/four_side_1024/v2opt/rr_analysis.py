"""Task 6/7 analysis: strengthened R&R ablation (E2/E3) and rip-up size yield.

Reads *only* the artefacts written by :mod:`four_side_1024.v2opt.pipeline`
(never re-runs the router) and produces

* ``experiments/figures_rr/*.png``     - matplotlib figures (Chinese labels)
* ``experiments/figures_rr/rr_analysis_data.json`` - every number behind them
* ``experiments/figures_rr/rr_tables.md``        - markdown tables (copied into
  ``ANALYSIS_RR.md``)

Zero fabrication: every value is either read from a summary/routes JSON, or
parsed out of the ``work/*.log`` file that the pipeline wrote.  Fields the
pipeline does not persist (e.g. per-transaction candidate evaluation counts)
are reported as *not recorded*, never guessed.

Usage
-----
    .venv\\Scripts\\python.exe -m four_side_1024.v2opt.rr_analysis
"""
from __future__ import annotations

import ast
import datetime
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / 'outputs/four_side_1024_v2_candidate_rr_v01'
EXPERIMENTS = OUT_ROOT / 'experiments'
FIG_DIR = EXPERIMENTS / 'figures_rr'
WORK_DIR = OUT_ROOT / 'work'

BASE_ROUTES = OUT_ROOT / 'planes' / 'V2' / 'BASE' / 'z2' / 'routes.json'

SIZES = (1, 2, 4, 8, 12)

# ---------------------------------------------------------------------------
# log line grammar (pipeline._log_to puts "HH:MM:SS " in front of every line)
# ---------------------------------------------------------------------------
RE_ROUND_START = re.compile(
    r'R&R round (\d+): pending=(\d+) analysing=(\d+) budget=(\d+) routed=(\d+)')
RE_ROUND_DONE = re.compile(
    r'R&R round (\d+) done: transactions=(\d+) improving=(\d+) '
    r'committed=(\d+) gain=(\d+) routed=(\d+) elapsed=([\d.]+)s')
RE_COMMIT = re.compile(r'commit (\d+)/k(\d+): (\d+) -> (\d+) \(\+(\d+)\)')
RE_BLOCKER = re.compile(r'blocker analysis: (\d+)/(\d+) elapsed=([\d.]+)s')
RE_TIME_LIMIT = re.compile(r'R&R: time limit reached before round (\d+)')
RE_SEQ = re.compile(
    r'sequential_commit: (\d+)/(\d+) applied=(\d+) routed=(\d+) elapsed=([\d.]+)s')
RE_SEQ_DONE = re.compile(r'E3 phase1 \(expanded sequential\): routed=(\d+)')
RE_CHECKPOINT = re.compile(r'checkpoint written .* routed=(\d+)')
RE_COMMAND = re.compile(r'command=(\{.*\})')

CJK_FONTS = ['Microsoft YaHei', 'SimHei', 'Noto Sans SC', 'FangSong', 'KaiTi']


def _setup_matplotlib():
    available = {font.name for font in font_manager.fontManager.ttflist}
    picked = [name for name in CJK_FONTS if name in available]
    plt.rcParams['font.sans-serif'] = picked + ['DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['figure.dpi'] = 130
    plt.rcParams['savefig.dpi'] = 160
    return picked


def _load_json(path):
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _log_start_epoch(name):
    match = re.search(r'_(\d{8})_(\d{6})\.log$', str(name))
    if not match:
        return None
    try:
        stamp = datetime.datetime.strptime(match.group(1) + match.group(2),
                                           '%Y%m%d%H%M%S')
    except ValueError:
        return None
    return stamp.timestamp()


def _iso_epoch(text):
    try:
        return datetime.datetime.fromisoformat(str(text)).timestamp()
    except (TypeError, ValueError):
        return None


def _load_plane_routes(label):
    payload = _load_json(OUT_ROOT / 'planes' / 'V2' / label / 'z2' / 'routes.json')
    if payload is None:
        return None
    routed = {int(record['route_id']) for record in payload['routes']
              if record.get('status') == 'routed'}
    failed = [record for record in payload['routes']
              if record.get('status') != 'routed']
    return dict(routed=routed, routed_count=len(routed), failed=failed,
                payload=payload)


def _parse_command(lines):
    """``pipeline`` logs ``command={'command': 'e2', ...}`` (a Python literal)."""
    for line in lines[:5]:
        marker = line.find('command=')
        if marker < 0:
            continue
        text = line[marker + len('command='):].strip()
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _find_log(command, label=None):
    """Latest work/*.log whose first line reports ``command`` (and ``label``)."""
    if not WORK_DIR.exists():
        return None
    candidates = []
    for path in WORK_DIR.glob('*.log'):
        try:
            first_lines = path.read_text(encoding='utf-8',
                                         errors='replace').splitlines()[:3]
        except OSError:
            continue
        parsed = _parse_command(first_lines)
        if parsed.get('command') != command:
            continue
        if label is not None and parsed.get('label') != label:
            continue
        candidates.append((path.stat().st_mtime, path, parsed))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _mtime, path, parsed = candidates[0]
    return dict(path=path, args=parsed, lines=path.read_text(
        encoding='utf-8', errors='replace').splitlines())


def _parse_rr_log(log, label):
    """Parse one pipeline log into round/commit/phase1 records."""
    commits = {size: [] for size in SIZES}
    unknown_sizes = Counter()
    rounds = {}
    order = 0
    current_round = 0
    round_start = None
    phase1 = dict(progress=[], final_routed=None)
    checkpoints = []
    time_limited = None
    seen_seq = False
    for line in log['lines']:
        if RE_COMMAND.search(line):
            continue
        if match := RE_SEQ.search(line):
            seen_seq = True
            phase1['progress'].append(dict(
                position=int(match.group(1)), total=int(match.group(2)),
                applied=int(match.group(3)), routed=int(match.group(4)),
                elapsed=float(match.group(5))))
            continue
        if match := RE_SEQ_DONE.search(line):
            seen_seq = True
            phase1['final_routed'] = int(match.group(1))
            continue
        if match := RE_ROUND_START.search(line):
            current_round = int(match.group(1))
            round_start = dict(
                round=current_round, pending=int(match.group(2)),
                analysing=int(match.group(3)), budget=int(match.group(4)),
                routed=int(match.group(5)))
            rounds.setdefault(current_round, {})['start'] = round_start
            continue
        if match := RE_BLOCKER.search(line):
            if current_round in rounds:
                rounds[current_round].setdefault('blocker_progress', []).append(
                    dict(done=int(match.group(1)), total=int(match.group(2)),
                         elapsed=float(match.group(3))))
            continue
        if match := RE_COMMIT.search(line):
            order += 1
            size = int(match.group(2))
            entry = dict(round=current_round, order=order,
                         target=int(match.group(1)), size=size,
                         before=int(match.group(3)), after=int(match.group(4)),
                         gain=int(match.group(5)))
            if size in commits:
                commits[size].append(entry)
            else:
                unknown_sizes[size] += 1
            continue
        if match := RE_ROUND_DONE.search(line):
            rounds.setdefault(int(match.group(1)), {})['done'] = dict(
                transactions=int(match.group(2)),
                improving=int(match.group(3)), committed=int(match.group(4)),
                gain=int(match.group(5)), routed=int(match.group(6)),
                elapsed=float(match.group(7)))
            continue
        if match := RE_TIME_LIMIT.search(line):
            time_limited = int(match.group(1))
            continue
        if match := RE_CHECKPOINT.search(line):
            checkpoints.append(int(match.group(1)))
    if unknown_sizes:
        print(f'[{label}] WARNING unknown k sizes in log: {dict(unknown_sizes)}')
    for size in commits:
        commits[size].sort(key=lambda entry: entry['order'])
    return dict(path=str(log['path']), args=log['args'],
                rounds=rounds, commits=commits, phase1=phase1,
                checkpoints=checkpoints, time_limited=time_limited,
                has_phase1=seen_seq)


def _k_table(parsed):
    """Per rip-up size k: number of committed transactions (= +1 route each)."""
    rows = []
    total = sum(len(parsed['commits'][size]) for size in parsed['commits'])
    total_gain = sum(entry['gain'] for size in parsed['commits']
                     for entry in parsed['commits'][size])
    for size in sorted(parsed['commits']):
        entries = parsed['commits'][size]
        gain = sum(entry['gain'] for entry in entries)
        rows.append(dict(
            k=size, committed=len(entries), gain=gain,
            share=(len(entries) / total) if total else 0.0,
            gain_share=(gain / total_gain) if total_gain else 0.0,
            multi_gain=sum(1 for entry in entries if entry['gain'] != 1),
            unique_targets=len({entry['target'] for entry in entries}),
            rounds=sorted({entry['round'] for entry in entries}),
            first_commit=min((entry['order'] for entry in entries), default=None),
        ))
    return dict(rows=rows, committed=total, gain=total_gain)


def _active_blockers(failed_records, accepted_ids):
    """Distribution of still-active blockers among the finally failed routes."""
    counts = []
    for record in failed_records:
        blockers = record.get('blockers') or {}
        active = sum(1 for key in blockers if int(key) in accepted_ids)
        counts.append(active)
    histogram = Counter(counts)
    cumulative = {}
    for size in SIZES:
        cumulative[size] = sum(1 for value in counts if value >= size)
    return dict(histogram={str(key): value for key, value in sorted(histogram.items())},
                cumulative_ge={str(size): cumulative[size] for size in SIZES},
                n=len(counts),
                mean=sum(counts) / len(counts) if counts else 0.0,
                total_active_blocker_links=sum(counts))


def _round_history(summary):
    """Per-round table from the summary history (pipeline ground truth)."""
    history = (summary or {}).get('history') or []
    rows = []
    for entry in history:
        rows.append(dict(round=int(entry['round']),
                         analysed=int(entry.get('analysed', 0)),
                         transactions=int(entry.get('transactions', 0)),
                         improving=int(entry.get('improving_results', 0)),
                         committed=int(entry.get('committed', 0)),
                         gain=int(entry.get('gain', 0)),
                         routed=int(entry.get('routed', 0)),
                         seconds=float(entry.get('seconds', 0.0))))
    return rows


def _annotate_rounds(history, initial_routed):
    """Derive per-round analysis-phase placements from the routed deltas.

    ``round routed - round start routed - round gain`` equals the routes that
    ``analyse_blockers`` placed directly (the pipeline does not add them to
    ``history.gain``).
    """
    previous = int(initial_routed)
    for row in history:
        row['start_routed'] = previous
        row['analysis_placements'] = (row['routed'] - previous - row['gain'])
        previous = row['routed']
    return history


def _experiment_record(label):
    summary = _load_json(EXPERIMENTS / f'{label}_z2_summary.json')
    plane = _load_plane_routes(label)
    record = dict(label=label, summary=summary, plane=plane,
                  available=summary is not None and plane is not None)
    return record


def _phase1_record():
    payload = _load_json(EXPERIMENTS / 'E3_phase1_summary.json')
    if payload is None:
        return dict(available=False)
    summary = payload.get('summary') or {}
    details = payload.get('routes') or []
    evaluated = sum(int(item.get('evaluated') or 0) for item in details)
    applied = [int(route_id) for route_id in summary.get('applied_route_ids') or []]
    seconds_per_route = [float(item.get('seconds') or 0.0) for item in details]
    progress = []
    cumulative_seconds = 0.0
    routed = 0
    for position, item in enumerate(details, 1):
        cumulative_seconds += float(item.get('seconds') or 0.0)
        if item.get('found'):
            routed += 1
        progress.append(dict(position=position, found=bool(item.get('found')),
                             routed=routed, cum_seconds=cumulative_seconds))
    return dict(available=True, summary=summary, evaluated=evaluated,
                attempted=int(summary.get('attempted', len(details))),
                applied=applied, applied_count=len(applied),
                routed=int(summary.get('routed', 0)),
                seconds=float(summary.get('seconds', 0.0)),
                mean_route_seconds=(sum(seconds_per_route) / len(seconds_per_route)
                                    if seconds_per_route else 0.0),
                max_route_seconds=max(seconds_per_route) if seconds_per_route else 0.0,
                progress=progress, details=details)


def _e1_record():
    summary = _load_json(EXPERIMENTS / 'E1_z2_summary.json')
    if summary is None:
        return dict(available=False, note='E1 summary not produced yet')
    plane = _load_plane_routes('E1')
    routed = int(summary.get('routed',
                             plane['routed_count'] if plane else -1))
    applied = [int(value) for value in summary.get('applied_route_ids') or []]
    return dict(available=True, routed=routed,
                attempted=summary.get('attempted'),
                applied=summary.get('applied'),
                applied_route_ids=applied,
                new_route_count=len(applied),
                seconds=float(summary.get('seconds', 0.0)),
                by_pair=(summary.get('route_summary') or {}).get('by_pair'),
                route_ids=(sorted(plane['routed']) if plane else []))


# ---------------------------------------------------------------------------
# data assembly
# ---------------------------------------------------------------------------
def collect():
    data = dict(generated_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                out_root=str(OUT_ROOT), sizes=list(SIZES))

    base_payload = _load_json(BASE_ROUTES)
    if base_payload is None:
        raise SystemExit(f'BASE routes missing: {BASE_ROUTES}')
    base_routed = {int(record['route_id']) for record in base_payload['routes']
                   if record.get('status') == 'routed'}
    base_failed = [record for record in base_payload['routes']
                   if record.get('status') != 'routed']
    base_stats = base_payload.get('statistics') or {}
    data['base'] = dict(
        routed=len(base_routed),
        total=len(base_payload['routes']),
        failed=len(base_failed),
        evaluated=((base_stats.get('source_run') or {}).get('candidate_evaluations')),
        seconds=((base_stats.get('source_run') or {}).get('runtime_seconds')),
        route_ids=sorted(base_routed))

    # ---- E2 ---------------------------------------------------------------
    e2 = _experiment_record('E2')
    e2_log_info = _find_log('e2')
    e2_parsed = _parse_rr_log(e2_log_info, 'E2') if e2_log_info else None
    data['e2'] = dict(available=e2['available'],
                      final_routed=(e2['summary'] or {}).get('final_routed'),
                      initial_routed=(e2['summary'] or {}).get('initial_routed'),
                      gain=(e2['summary'] or {}).get('gain'),
                      seconds=(e2['summary'] or {}).get('seconds'),
                      history=_round_history(e2['summary']),
                      route_summary=(e2['summary'] or {}).get('route_summary'),
                      log=e2_parsed['path'] if e2_parsed else None,
                      log_args=e2_parsed['args'] if e2_parsed else None,
                      phase1=None)
    if e2['available']:
        _annotate_rounds(data['e2']['history'], data['e2']['initial_routed'] or 0)
        new_ids = sorted(e2['plane']['routed'] - base_routed)
        transaction_gain = sum(row['gain'] for row in data['e2']['history'])
        data['e2'].update(
            new_route_ids=new_ids, new_route_count=len(new_ids),
            transaction_gain=transaction_gain,
            analysis_placements=(int(e2['summary']['final_routed'])
                                 - int(e2['summary']['initial_routed'])
                                 - transaction_gain),
            still_failed_ids=sorted(
                int(record['route_id']) for record in e2['plane']['failed']),
            still_failed_count=len(e2['plane']['failed']),
            active_blockers=_active_blockers(e2['plane']['failed'],
                                             e2['plane']['routed']))
    if e2_parsed:
        data['e2']['k_table'] = _k_table(e2_parsed)
        data['e2']['log_rounds'] = [
            dict(round=number, **value)
            for number, value in sorted(e2_parsed['rounds'].items())]

    # ---- E3 ---------------------------------------------------------------
    e3 = _experiment_record('E3')
    phase1 = _phase1_record()
    e3_log_info = _find_log('e3')
    e3_parsed = _parse_rr_log(e3_log_info, 'E3') if e3_log_info else None
    data['e3_phase1'] = dict(
        available=phase1['available'],
        routed=phase1.get('routed'),
        applied_count=phase1.get('applied_count'),
        applied_route_ids=phase1.get('applied'),
        attempted=phase1.get('attempted'),
        evaluated=phase1.get('evaluated'),
        seconds=phase1.get('seconds'),
        mean_route_seconds=phase1.get('mean_route_seconds'),
        max_route_seconds=phase1.get('max_route_seconds'),
        progress=phase1.get('progress') or [])
    data['e3'] = dict(available=e3['available'],
                      final_routed=(e3['summary'] or {}).get('final_routed'),
                      initial_routed=(e3['summary'] or {}).get('initial_routed'),
                      gain=(e3['summary'] or {}).get('gain'),
                      seconds=(e3['summary'] or {}).get('seconds'),
                      history=_round_history(e3['summary']),
                      route_summary=(e3['summary'] or {}).get('route_summary'),
                      log=e3_parsed['path'] if e3_parsed else None,
                      log_args=e3_parsed['args'] if e3_parsed else None,
                      phase1=dict(routed=phase1.get('routed'),
                                  seconds=phase1.get('seconds')) if phase1['available'] else None)
    if e3['available']:
        _annotate_rounds(data['e3']['history'], data['e3']['initial_routed'] or 0)
        new_ids = sorted(e3['plane']['routed'] - base_routed)
        phase1_ids = set(phase1.get('applied') or []) if phase1['available'] else set()
        rr_only = sorted((e3['plane']['routed'] - base_routed) - phase1_ids)
        transaction_gain = sum(row['gain'] for row in data['e3']['history'])
        data['e3'].update(
            new_route_ids=new_ids, new_route_count=len(new_ids),
            rr_only_new_route_ids=rr_only, rr_only_new_count=len(rr_only),
            transaction_gain=transaction_gain,
            analysis_placements=(int(e3['summary']['final_routed'])
                                 - int(e3['summary']['initial_routed'])
                                 - transaction_gain),
            still_failed_ids=sorted(
                int(record['route_id']) for record in e3['plane']['failed']),
            still_failed_count=len(e3['plane']['failed']),
            active_blockers=_active_blockers(e3['plane']['failed'],
                                             e3['plane']['routed']))
    if e3_parsed:
        data['e3']['k_table'] = _k_table(e3_parsed)
        data['e3']['log_rounds'] = [
            dict(round=number, **value)
            for number, value in sorted(e3_parsed['rounds'].items())]

    # ---- E3X: Lead's R&R continuation (separate protocol, extension arm) ---
    e3x = _experiment_record('E3X')
    e3x_log_info = _find_log('rrcontinue', label='E3X')
    e3x_parsed = _parse_rr_log(e3x_log_info, 'E3X') if e3x_log_info else None
    data['e3x'] = dict(available=e3x['available'],
                       initial_routed=(e3x['summary'] or {}).get('initial_routed'),
                       final_routed=(e3x['summary'] or {}).get('final_routed'),
                       gain=(e3x['summary'] or {}).get('gain'),
                       seconds=(e3x['summary'] or {}).get('seconds'),
                       history=_round_history(e3x['summary']),
                       continued_from=(e3x['summary'] or {}).get('continued_from'),
                       seed=(e3x['summary'] or {}).get('seed'),
                       route_summary=(e3x['summary'] or {}).get('route_summary'),
                       log=e3x_parsed['path'] if e3x_parsed else None,
                       log_args=e3x_parsed['args'] if e3x_parsed else None)
    if e3x['available']:
        _annotate_rounds(data['e3x']['history'],
                         data['e3x']['initial_routed'] or 0)
        sizes_list = ((e3x_parsed['args'] or {}).get('sizes')
                      if e3x_parsed else None) or list(SIZES)
        for row in data['e3x']['history']:
            row['k_used'] = sizes_list[min(row['round'] - 1,
                                           len(sizes_list) - 1)]
        new_ids = sorted(e3x['plane']['routed'] - base_routed)
        e3_ids = set(e3['plane']['routed']) if e3['available'] else set()
        extension_ids = sorted(e3x['plane']['routed'] - e3_ids)
        transaction_gain = sum(row['gain'] for row in data['e3x']['history'])
        data['e3x'].update(
            sizes=sizes_list,
            new_route_ids=new_ids, new_route_count=len(new_ids),
            extension_new_route_ids=extension_ids,
            extension_new_count=len(extension_ids),
            transaction_gain=transaction_gain,
            analysis_placements=(int(e3x['summary']['final_routed'])
                                 - int(e3x['summary']['initial_routed'])
                                 - transaction_gain),
            still_failed_ids=sorted(
                int(record['route_id']) for record in e3x['plane']['failed']),
            still_failed_count=len(e3x['plane']['failed']))
    if e3x_parsed:
        data['e3x']['k_table'] = _k_table(e3x_parsed)
        data['e3x']['log_rounds'] = [
            dict(round=number, **value)
            for number, value in sorted(e3x_parsed['rounds'].items())]

    # ---- per-experiment k yield vs feasibility in the final layout ---------
    for key in ('e2', 'e3', 'e3x'):
        record = data.get(key) or {}
        blockers = record.get('active_blockers')
        table = record.get('k_table')
        if not blockers or not table:
            continue
        for row in table['rows']:
            feasible = blockers['cumulative_ge'].get(str(row['k']), 0)
            row['feasible_targets_final'] = feasible
            row['commits_per_100_feasible'] = (
                100.0 * row['committed'] / feasible if feasible else 0.0)

    # ---- combined k table (E2 + E3) --------------------------------------
    combined = {size: dict(k=size, committed=0, gain=0, experiments=[])
                for size in SIZES}
    for label in ('e2', 'e3'):
        table = (data.get(label) or {}).get('k_table')
        if not table:
            continue
        for row in table['rows']:
            if row['k'] in combined:
                combined[row['k']]['committed'] += row['committed']
                combined[row['k']]['gain'] += row['gain']
                combined[row['k']]['experiments'].append(
                    dict(label=label.upper(), committed=row['committed'],
                         gain=row['gain']))
    committed_total = sum(item['committed'] for item in combined.values())
    for item in combined.values():
        item['share'] = (item['committed'] / committed_total
                         if committed_total else 0.0)
    data['k_combined'] = dict(
        rows=[combined[size] for size in SIZES], committed=committed_total)

    # ---- E1 (produced by the Lead; optional cross-check) ------------------
    data['e1'] = _e1_record()

    # ---- Z1OPT (already produced; different plane => context only) --------
    z1opt = _load_json(EXPERIMENTS / 'Z1OPT_z1_summary.json')
    if z1opt:
        data['z1opt'] = dict(available=True, plane=z1opt.get('plane'),
                             initial_plane_baseline=492,
                             initial=z1opt.get('initial'), final=z1opt.get('final'),
                             gain=z1opt.get('gain'),
                             sequential=z1opt.get('sequential') or {},
                             ripup=z1opt.get('ripup') or {})
    else:
        data['z1opt'] = dict(available=False)

    # ---- staleness guard: a re-run log newer than the summary artefact ----
    warnings = []
    for label in ('e2', 'e3', 'e3x'):
        plane = _load_plane_routes(label)
        log_path = data[label].get('log')
        if not plane or not log_path:
            continue
        checkpoint = _load_json(OUT_ROOT / 'planes' / 'V2' / label / 'z2'
                                / 'CHECKPOINT.json')
        timestamp = (checkpoint or {}).get('timestamp')
        log_start = _log_start_epoch(Path(log_path).name)
        checkpoint_epoch = _iso_epoch(timestamp) if timestamp else None
        if checkpoint_epoch is not None and log_start is not None \
                and checkpoint_epoch < log_start:
            warnings.append(
                f'{label.upper()}: summary/CHECKPOINT ({timestamp}) 早于当前日志 '
                f'{Path(log_path).name}，说明该实验已重跑但结果尚未落盘，'
                f'当前数字不可用')
        data[label]['checkpoint_timestamp'] = timestamp
    data['warnings'] = warnings
    if warnings:
        print('WARNING:')
        for warning in warnings:
            print('  ' + warning)

    # ---- cross-experiment route-set comparison ---------------------------
    e1 = data.get('e1') or {}
    e1_new = (set(e1.get('route_ids') or []) - base_routed
              if e1.get('available') else set())
    comparison = dict(e1_new_count=len(e1_new) if e1_new else None, per=dict())
    for label in ('e2', 'e3', 'e3x'):
        record = data.get(label) or {}
        target = set(record.get('new_route_ids') or [])
        if not target:
            continue
        entry = dict(new_count=len(target))
        if e1_new:
            entry.update(overlap_e1_new=len(target & e1_new),
                         not_in_e1=len(target - e1_new),
                         e1_new_not_in_experiment=len(e1_new - target))
        comparison['per'][label] = entry
    data['comparison'] = comparison

    # ---- cross-checks with the pipeline's own round records ---------------
    checks = []
    for label in ('e2', 'e3', 'e3x'):
        record = data[label]
        parsed = {'e2': e2_parsed, 'e3': e3_parsed, 'e3x': e3x_parsed}.get(label)
        if not parsed:
            continue
        logged = sum(len(parsed['commits'][size]) for size in parsed['commits'])
        summary_committed = sum(row['committed'] for row in record['history'])
        logged_gain = sum(entry['gain'] for size in parsed['commits']
                          for entry in parsed['commits'][size])
        summary_gain = sum(row['gain'] for row in record['history'])
        checks.append(dict(label=label.upper(),
                           log_committed=logged,
                           summary_committed=summary_committed,
                           log_gain=logged_gain, summary_gain=summary_gain,
                           consistent=(logged == summary_committed
                                       and logged_gain == summary_gain)))
    data['cross_checks'] = checks
    return data


# ---------------------------------------------------------------------------
# controlled k-scale replay (diagnostic, re-uses the shipped R&R machinery)
# ---------------------------------------------------------------------------
HIST_ROUTES = (ROOT / 'outputs/four_side_1024_fslw_R40_gap30_abcd'
               / 'planes/V2/C/z2/routes.json')
E3_PHASE1_CHECKPOINT = OUT_ROOT / 'checkpoints' / 'E3_phase1_z2.json'
K_REPLAY_PATH = FIG_DIR / 'rr_k_replay.json'


def _replay_layout(kind):
    """Load a frozen layout + the experiment's exact per-transaction settings."""
    from .core import LayoutState, load_layout_from_checkpoint
    if kind == 'base':
        state = LayoutState.from_history('V2', 'z2', HIST_ROUTES, log=print)
        config = dict(budget=200, reinsert_budget=200, use_expanded=False,
                      max_evals_per_transaction=12000,
                      transaction_seconds=90.0)
        note = ('BASE 206/512（历史 V2-C）。E2 官方 config: budget=200、'
                'reinsert_budget=min(200,400)=200、原始候选生成器')
    elif kind in ('e3phase1', 'e3_phase1'):
        state = load_layout_from_checkpoint('V2', 'z2', E3_PHASE1_CHECKPOINT,
                                            log=print)
        config = dict(budget=1600, reinsert_budget=800, use_expanded=True,
                      max_evals_per_transaction=12000,
                      transaction_seconds=90.0)
        note = ('E3 phase1 243/512（从 checkpoints/E3_phase1_z2.json 重建）。'
                'E3 官方 config: budget=1600、reinsert_budget=min(1600,800)=800、'
                '扩展候选生成器')
    else:
        raise ValueError('unknown replay layout ' + str(kind))
    config['note'] = note
    return state, config


def _replay_targets(state, count, mode):
    """Same target ranking as rr.ripup_reroute, but both extremes for coverage."""
    pending = [route['route_id'] for route in state.routes
               if route['route_id'] not in state.accepted]
    with_blockers = [route_id for route_id in pending
                     if state.failure_blockers(route_id)]
    if mode == 'fewest':
        with_blockers.sort(key=lambda route_id: (
            len(state.failure_blockers(route_id)),
            -len(state.failed.get(route_id, {}).get('blockers') or {})))
    elif mode == 'most':
        with_blockers.sort(key=lambda route_id: (
            -len(state.failure_blockers(route_id)),
            len(state.failed.get(route_id, {}).get('blockers') or {})))
    else:
        raise ValueError('unknown target mode ' + str(mode))
    targets = with_blockers[:count]
    info = dict(mode=mode, candidates_with_blockers=len(with_blockers),
                selected=len(targets),
                blocker_counts=[len(state.failure_blockers(route_id))
                                for route_id in targets])
    return targets, info


def _replay_worker(task):
    """Multiprocessing worker: execute a list of transactions on one frozen dump."""
    from . import rr as RR
    dump = task['dump']
    config = task['config']
    results = []
    for transaction in task['transactions']:
        payload = dict(dump=dump, transaction=transaction,
                       budget=config['budget'],
                       reinsert_budget=config['reinsert_budget'],
                       max_evals_per_transaction=config['max_evals_per_transaction'],
                       transaction_seconds=config['transaction_seconds'],
                       use_expanded=config['use_expanded'],
                       seed=transaction['seed'], cfg=task['cfg'])
        started = time.perf_counter()
        try:
            result = RR.execute_transaction(payload)
        except Exception as exc:  # noqa: BLE001 - replay must survive bad tx
            result = dict(transaction=transaction,
                          error=f'{type(exc).__name__}: {exc}',
                          net_gain=-10 ** 9, placed={}, ripped=[],
                          target_placed=False, failed_reinsert=[], evals=0,
                          seconds=0.0)
        result['wall_seconds'] = time.perf_counter() - started
        results.append(result)
    return results


def _replay_aggregate(results):
    """Per-k outcome statistics of one replay arm."""
    per_k = {size: dict(k=size, attempted=0, target_placed=0, improving=0,
                        zero_gain=0, negative=0, errors=0, evals=0,
                        seconds=0.0) for size in SIZES}
    failed_reinsert_hist = Counter()
    for result in results:
        transaction = result['transaction']
        size = int(transaction['size'])
        entry = per_k.setdefault(size, dict(k=size, attempted=0, target_placed=0,
                                            improving=0, zero_gain=0, negative=0,
                                            errors=0, evals=0, seconds=0.0))
        entry['attempted'] += 1
        entry['evals'] += int(result.get('evals') or 0)
        entry['seconds'] += float(result.get('wall_seconds') or 0.0)
        if result.get('error'):
            entry['errors'] += 1
            continue
        if result.get('target_placed'):
            entry['target_placed'] += 1
        gain = int(result.get('net_gain', 0))
        if gain > 0:
            entry['improving'] += 1
        elif gain == 0:
            entry['zero_gain'] += 1
        else:
            entry['negative'] += 1
        failed = len(result.get('failed_reinsert') or [])
        failed_reinsert_hist[f'{size}:{failed}'] += 1
    rows = []
    for size in sorted(per_k):
        entry = per_k[size]
        entry['target_placed_rate'] = (entry['target_placed'] / entry['attempted']
                                       if entry['attempted'] else 0.0)
        entry['improving_rate'] = (entry['improving'] / entry['attempted']
                                   if entry['attempted'] else 0.0)
        entry['mean_evals'] = (entry['evals'] / entry['attempted']
                               if entry['attempted'] else 0.0)
        entry['mean_seconds'] = (entry['seconds'] / entry['attempted']
                                 if entry['attempted'] else 0.0)
        rows.append(entry)
    return rows, dict(failed_reinsert_hist)


def _parse_replay_plan(text):
    """``base:A48;e3phase1:A48,B16`` -> [(layout, arm, target_count), ...]."""
    plan = []
    for chunk in str(text).split(';'):
        chunk = chunk.strip()
        if not chunk:
            continue
        layout, _, arms = chunk.partition(':')
        layout = layout.strip()
        if not arms:
            plan.append((layout, 'A_fewest_blockers', 48))
            continue
        for arm_spec in arms.split(','):
            arm_spec = arm_spec.strip()
            if not arm_spec:
                continue
            arm = ('A_fewest_blockers' if arm_spec[0] in ('A', 'a')
                   else 'B_most_blockers')
            count = int(arm_spec[1:] or 0)
            if count > 0:
                plan.append((layout, arm, count))
    return plan


def run_k_replay(plan=(('base', 'A_fewest_blockers', 48),
                       ('e3phase1', 'A_fewest_blockers', 48),
                       ('e3phase1', 'B_most_blockers', 16)),
                 workers=6):
    """Replay **all** transactions the shipped builder would emit for one round.

    The official pipeline samples only 64 transactions per round and merges
    commits sequentially, so per-k denominators are unknown.  This diagnostic
    freezes one layout, builds the complete transaction set of a round (same
    builder, same seed, same budgets) and measures the outcome of *every*
    transaction independently, giving a controlled per-k comparison.
    """
    from multiprocessing import Pool
    from . import rr as RR
    from . import config as V

    replay = dict(generated_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                  purpose='受控 k 规模对照重放：冻结布局上执行一轮 RR.build_transactions '
                          '生成的**全部**交易（官方每轮只随机采样 64 笔），'
                          '统计每个 k 的目标插入/全部回插/净增益成功率',
                  seed_note='交易构造 seed = V.SEED + round_index（round_index=1，'
                            '与官方首轮一致）；B 组额外加 1000',
                  layouts={})
    started_all = time.perf_counter()
    layouts_order = []
    for layout_name, _arm, _count in plan:
        if layout_name not in layouts_order:
            layouts_order.append(layout_name)
    for kind in layouts_order:
        print(f'[{kind}] loading frozen layout ...')
        state, config = _replay_layout(kind)
        routed = len(state.accepted)
        layout_entry = dict(kind=kind, routed=routed,
                            total=len(state.routes),
                            failed_records=len(state.failed),
                            config=dict(config), arms={})
        transactions = []
        for layout_name, arm, arm_targets in plan:
            if layout_name != kind:
                continue
            mode = ('fewest' if arm == 'A_fewest_blockers' else 'most')
            seed_shift = 0 if arm == 'A_fewest_blockers' else 1000
            targets, info = _replay_targets(state, arm_targets, mode)
            arm_transactions = RR.build_transactions(
                state, targets, sizes=tuple(SIZES), per_route=2,
                seed=V.SEED + 1 + seed_shift)
            for index, transaction in enumerate(arm_transactions):
                transaction['arm'] = arm
                transaction['seed'] = V.SEED + 1 * 7919 + len(transactions) + index
            transactions.extend(arm_transactions)
            layout_entry['arms'][arm] = dict(
                targets=info, transactions=len(arm_transactions),
                target_config=dict(budget=config['budget'],
                                   reinsert_budget=config['reinsert_budget']))
            print(f'[{kind}] arm {arm}: targets={info["selected"]} '
                  f'(blockers {min(info["blocker_counts"]) if info["blocker_counts"] else 0}'
                  f'..{max(info["blocker_counts"]) if info["blocker_counts"] else 0}) '
                  f'transactions={len(arm_transactions)}')
        dump = state.dump()
        worker_count = max(1, min(int(workers), len(transactions)))
        buckets = [[] for _ in range(worker_count)]
        for index, transaction in enumerate(transactions):
            buckets[index % worker_count].append(transaction)
        tasks = [dict(dump=dump, config=config, cfg=state.cfg,
                      transactions=bucket)
                 for bucket in buckets if bucket]
        print(f'[{kind}] executing {len(transactions)} transactions on '
              f'{len(tasks)} workers ...', flush=True)
        started = time.perf_counter()
        results = []
        with Pool(processes=len(tasks)) as pool:
            for chunk_index, chunk in enumerate(
                    pool.imap_unordered(_replay_worker, tasks), 1):
                results.extend(chunk)
                print(f'[{kind}] worker chunk {chunk_index}/{len(tasks)} done '
                      f'({len(results)}/{len(transactions)} tx, '
                      f'{time.perf_counter() - started:.0f}s)', flush=True)
        layout_entry['seconds'] = time.perf_counter() - started
        layout_entry['transactions_executed'] = len(results)
        by_arm = {}
        for arm in ('A_fewest_blockers', 'B_most_blockers'):
            arm_results = [result for result in results
                           if result['transaction'].get('arm') == arm]
            rows, extra = _replay_aggregate(arm_results)
            by_arm[arm] = dict(rows=rows, **extra)
        layout_entry['arms_results'] = by_arm
        replay['layouts'][kind] = layout_entry
        print(f'[{kind}] replay done in {layout_entry["seconds"]:.0f}s', flush=True)
    replay['seconds_total'] = time.perf_counter() - started_all
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    K_REPLAY_PATH.write_text(json.dumps(replay, indent=1, ensure_ascii=False),
                             encoding='utf-8')
    print(f'k replay written {K_REPLAY_PATH}')
    return replay


def _load_k_replay():
    return _load_json(K_REPLAY_PATH)


def figure_k_replay(data):
    """受控重放：每个 k 的目标插入成功率 / 全部回插（净增益）成功率."""
    replay = data.get('k_replay')
    if not replay:
        return None
    layouts = replay.get('layouts') or {}
    keys = [key for key in ('base', 'e3phase1') if key in layouts]
    if not keys:
        return None
    titles = {'base': 'BASE 206/512（E2 交易参数：budget=200/回插=200）',
              'e3phase1': 'E3 phase1 243/512（E3 交易参数：budget=1600/回插=800）'}
    arms = (('A_fewest_blockers', 'A 组：blocker 最少的目标', '#4C72B0'),
            ('B_most_blockers', 'B 组：blocker 最多的目标', '#DD8452'))
    fig, axes = plt.subplots(len(keys), 2, figsize=(12.5, 4.2 * len(keys)),
                             squeeze=False)
    for row, key in enumerate(keys):
        layout = layouts[key]
        for col, (arm, arm_label, color) in enumerate(arms):
            ax = axes[row][col]
            rows = ((layout.get('arms_results') or {}).get(arm) or {}).get('rows') or []
            rows = [entry for entry in rows if entry['attempted'] > 0]
            if not rows:
                ax.set_visible(False)
                continue
            sizes = [entry['k'] for entry in rows]
            positions = range(len(sizes))
            width = 0.38
            placed = [entry['target_placed_rate'] * 100 for entry in rows]
            improving = [entry['improving_rate'] * 100 for entry in rows]
            bars_a = ax.bar([pos - width / 2 for pos in positions], placed, width,
                            label='目标插入成功', color=color, alpha=0.45)
            bars_b = ax.bar([pos + width / 2 for pos in positions], improving, width,
                            label='全部回插成功（净增益 +1）', color=color)
            for pos, entry in enumerate(rows):
                ax.annotate(f"{entry['improving']}/{entry['attempted']}",
                            (pos + width / 2, entry['improving_rate'] * 100),
                            textcoords='offset points', xytext=(0, 4),
                            ha='center', fontsize=7)
                ax.annotate(f"{entry['target_placed']}/{entry['attempted']}",
                            (pos - width / 2, entry['target_placed_rate'] * 100),
                            textcoords='offset points', xytext=(0, 4),
                            ha='center', fontsize=7)
            ax.set_xticks(list(positions))
            ax.set_xticklabels([f'k={size}' for size in sizes])
            ax.set_ylim(0, 108)
            ax.set_ylabel('成功率 / %')
            ax.set_title(f'{titles.get(key, key)}\n{arm_label}')
            ax.grid(axis='y', alpha=0.3)
            ax.legend(fontsize=7, loc='upper right')
    fig.suptitle('k 规模受控重放：单笔交易成功率（标注 = 成功数/尝试数）', y=1.02)
    return _save(fig, 'fig_k_replay_yield.png')


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------
def _save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / name
    fig.tight_layout()
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    return path


def figure_k_scale(data):
    """拆线规模 k vs 新增布通：committed transactions (= +1 route) 与贡献占比."""
    rows = data['k_combined']['rows']
    if not rows:
        return None
    sizes = [row['k'] for row in rows]
    total = sum(row['committed'] for row in rows)
    if total == 0 and not (data.get('e2', {}).get('available')
                           or data.get('e3', {}).get('available')):
        return None
    if total == 0:
        return None
    per_experiment = {'E2': {}, 'E3': {}, 'E3X': {}}
    for row in rows:
        for entry in row['experiments']:
            per_experiment[entry['label']][row['k']] = entry['committed']
    e3x_record = data.get('e3x') or {}
    if e3x_record.get('k_table'):
        for row in e3x_record['k_table']['rows']:
            per_experiment['E3X'][row['k']] = row['gain']
    e2, e3 = per_experiment['E2'], per_experiment['E3']
    e3x = per_experiment['E3X']
    committed = [row['committed'] for row in rows]
    total = sum(committed)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.4))
    width = 0.27
    x = range(len(sizes))
    e2_vals = [e2.get(size, 0) for size in sizes]
    e3_vals = [e3.get(size, 0) for size in sizes]
    e3x_vals = [e3x.get(size, 0) for size in sizes]
    bars1 = ax1.bar([pos - width for pos in x], e2_vals, width,
                    label='E2（原始候选+R&R）', color='#4C72B0')
    bars2 = ax1.bar(list(x), e3_vals, width,
                    label='E3（扩展候选+R&R）', color='#DD8452')
    bars3 = ax1.bar([pos + width for pos in x], e3x_vals, width,
                    label='E3X（R&R 延伸，按轮升级 k）', color='#C44E52')
    ax1.bar_label(bars1, fontsize=7)
    ax1.bar_label(bars2, fontsize=7)
    ax1.bar_label(bars3, fontsize=7)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels([f'k={size}' for size in sizes])
    ax1.set_ylabel('R&R 成功提交交易数（每笔 +1 条起）')
    ax1.set_title(f'拆线规模 k vs 新增布通（E2+E3 官方臂合计 {total} 条）')
    ax1.legend(fontsize=7)
    ax1.grid(axis='y', alpha=0.3)

    cumulative = 0
    ys = []
    labels = []
    for size, count in zip(sizes, committed):
        cumulative += count
        ys.append(cumulative / total * 100)
        labels.append(f'{cumulative}')
    ax2.plot(list(x), ys, marker='o', color='#55A868', linewidth=2)
    for pos, (value, label) in enumerate(zip(ys, labels)):
        ax2.annotate(f'{label} 条\n{value:.1f}%', (pos, value),
                     textcoords='offset points', xytext=(0, 8),
                     ha='center', fontsize=8)
    ax2.set_xticks(list(x))
    ax2.set_xticklabels([f'k={size}' for size in sizes])
    ax2.set_ylabel('累计占比 / %')
    ax2.set_title('累计收益随 k 的变化')
    ax2.set_ylim(0, 108)
    ax2.grid(alpha=0.3)
    return _save(fig, 'fig_k_scale_gain.png')


def figure_rounds_curve(data):
    """R&R 轮次 vs routed 累计曲线."""
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    series = []
    if data['e2']['available']:
        history = data['e2']['history']
        ys = [data['base']['routed']] + [row['routed'] for row in history]
        xs = list(range(0, len(ys)))
        series.append(('E2（原始候选+R&R）', xs, ys, '#4C72B0'))
    if data['e3']['available'] and data['e3_phase1']['available']:
        history = data['e3']['history']
        start = data['e3_phase1']['routed']
        ys = [start] + [row['routed'] for row in history]
        xs = list(range(0, len(ys)))
        series.append(('E3（扩展候选+R&R）', xs, ys, '#DD8452'))
        ax.axhline(start, color='#DD8452', linestyle=':', linewidth=1.2)
        ax.annotate(f'E3 顺序插入阶段 = {start}', xy=(0, start),
                    xytext=(0.35, start - 8), fontsize=9, color='#DD8452')
    e1 = data.get('e1') or {}
    if e1.get('available'):
        ax.axhline(e1['routed'], color='#55A868', linestyle='--', linewidth=1.2,
                   label=f"E1 最终 {e1['routed']}")
    e3x = data.get('e3x') or {}
    if e3x.get('available') and e3x.get('history'):
        start = e3x.get('initial_routed') or data['e3']['final_routed']
        ys = [start] + [row['routed'] for row in e3x['history']]
        xs = list(range(0, len(ys)))
        series.append(('E3X（R&R 延伸）', xs, ys, '#C44E52'))
    for label, xs, ys, color in series:
        ax.plot(xs, ys, marker='o', label=label, color=color, linewidth=2)
        for x_value, y_value in zip(xs, ys):
            ax.annotate(str(y_value), (x_value, y_value),
                        textcoords='offset points', xytext=(0, 7),
                        ha='center', fontsize=8, color=color)
    ax.axhline(data['base']['routed'], color='#8172B3', linestyle='--',
               linewidth=1.2, label=f"BASE {data['base']['routed']}")
    ax.set_xlabel('R&R 轮次（0 = R&R 开始前）')
    max_x = max((xs[-1] for _label, xs, _ys, _color in series), default=1)
    ax.set_xticks(list(range(0, max_x + 1)))
    ax.set_ylim(200, max([max(ys) for _label, _xs, ys, _color in series]) + 8)
    ax.set_ylabel('累计已布通路线数 / 512')
    ax.set_title('强化 R&R 轮次累计布通曲线')
    ax.grid(alpha=0.3)
    ax.legend(loc='lower right')
    return _save(fig, 'fig_rr_rounds_curve.png')


def figure_experiment_compare(data):
    """E1/E2/E3 与 BASE 对比柱状."""
    entries = [('BASE', data['base']['routed'], '#8172B3')]
    e1 = data.get('e1') or {}
    if e1.get('available'):
        entries.append(('E1\n扩展候选贪心', e1['routed'], '#55A868'))
    if data['e3_phase1']['available']:
        entries.append(('E3 phase1\n顺序插入', data['e3_phase1']['routed'], '#C44E52'))
    if data['e2']['available']:
        entries.append(('E2\n原始+R&R', data['e2']['final_routed'], '#4C72B0'))
    if data['e3']['available']:
        entries.append(('E3\n扩展+R&R', data['e3']['final_routed'], '#DD8452'))
    e3x = data.get('e3x') or {}
    if e3x.get('available'):
        entries.append(('E3X\nR&R 延伸', e3x['final_routed'], '#C44E52'))
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    names = [item[0] for item in entries]
    values = [item[1] for item in entries]
    colors = [item[2] for item in entries]
    bars = ax.bar(names, values, color=colors, width=0.6)
    ax.bar_label(bars, fontsize=9, fontweight='bold')
    base = data['base']['routed']
    for position, (name, value, _color) in enumerate(entries):
        if name == 'BASE':
            continue
        ax.annotate(f'+{value - base}', (position, value),
                    textcoords='offset points', xytext=(0, -18),
                    ha='center', fontsize=9, color='#333333')
    if e3x.get('available') and data['e3'].get('available'):
        position = len(entries) - 1
        delta = e3x['final_routed'] - data['e3']['final_routed']
        ax.annotate(f"相对 E3 {delta:+d}", (position, e3x['final_routed']),
                    textcoords='offset points', xytext=(0, -34),
                    ha='center', fontsize=8, color='#C44E52')
    ax.axhline(base, color='#8172B3', linestyle='--', linewidth=1.1)
    ax.set_ylim(0, max(values) * 1.18 or 1)
    ax.set_ylabel('已布通路线数 / 512')
    ax.set_title('E1/E2/E3/E3X 消融实验对比（同一 BASE 布局 z2）')
    ax.grid(axis='y', alpha=0.3)
    return _save(fig, 'fig_experiment_compare.png')


def figure_round_gain(data):
    """每轮 committed / improving / gain：饱和趋势."""
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.3), sharey=False)
    panels = [('e2', 'E2（原始候选+R&R）', '#4C72B0', axes[0]),
              ('e3', 'E3（扩展候选+R&R，首轮即早停）', '#DD8452', axes[1]),
              ('e3x', 'E3X（R&R 延伸，k 按轮升级）', '#C44E52', axes[2])]
    for key, title, color, ax in panels:
        record = data.get(key) or {}
        if not record.get('available') or not record['history']:
            ax.set_visible(False)
            continue
        history = record['history']
        rounds = [row['round'] for row in history]
        gain = [row['gain'] for row in history]
        improving = [row['improving'] for row in history]
        committed = [row['committed'] for row in history]
        positions = range(len(rounds))
        width = 0.27
        bars_a = ax.bar([pos - width for pos in positions], improving, width,
                        label='improving 交易候选', color=color, alpha=0.35)
        bars_b = ax.bar(positions, committed, width,
                        label='实际 commit', color=color, alpha=0.7)
        bars_c = ax.bar([pos + width for pos in positions], gain, width,
                        label='本轮净增 routed', color='black', alpha=0.85)
        for bars in (bars_a, bars_b, bars_c):
            ax.bar_label(bars, fontsize=7)
        if key == 'e3x':
            labels = [f"轮{r}\nk={row.get('k_used', '?')}"
                      for r, row in zip(rounds, history)]
        else:
            labels = [f'轮{r}' for r in rounds]
        ax.set_xticks(list(positions))
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_title(title)
        ax.set_ylabel('数量')
        ax.grid(axis='y', alpha=0.3)
        ax.legend(fontsize=7)
    fig.suptitle('每轮 R&R 产出与饱和趋势', y=1.02)
    return _save(fig, 'fig_round_gain_saturation.png')


def figure_phase1_progress(data):
    """E3 顺序插入阶段（1600 预算）进度：累计布通 vs 尝试路线数与耗时."""
    phase1 = data.get('e3_phase1') or {}
    progress = phase1.get('progress') or []
    if not phase1.get('available') or not progress:
        return None
    positions = [row['position'] for row in progress]
    routed = [row['routed'] for row in progress]
    seconds = [row['cum_seconds'] for row in progress]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.3))
    ax1.plot(positions, routed, color='#C44E52', linewidth=2)
    ax1.axhline(data['base']['routed'], color='#8172B3', linestyle='--',
                linewidth=1.1, label=f"BASE {data['base']['routed']}")
    ax1.annotate(f"最终 {routed[-1]}", (positions[-1], routed[-1]),
                 textcoords='offset points', xytext=(-40, 8), fontsize=9,
                 color='#C44E52')
    ax1.set_xlabel('尝试顺序（失败路线编号）')
    ax1.set_ylabel('累计已布通路线数')
    ax1.set_title('E3 phase1 顺序插入：累计布通进度')
    ax1.grid(alpha=0.3)
    ax1.legend()
    ax2.plot(seconds, routed, color='#DD8452', linewidth=2)
    ax2.axhline(data['base']['routed'], color='#8172B3', linestyle='--',
                linewidth=1.1)
    ax2.set_xlabel('累计耗时 / s')
    ax2.set_ylabel('累计已布通路线数')
    ax2.set_title(f"E3 phase1 布通 vs 耗时（总 {phase1['seconds']:.0f}s）")
    ax2.grid(alpha=0.3)
    return _save(fig, 'fig_e3_phase1_progress.png')


def figure_k_availability(data):
    records = []
    if data['e2'].get('active_blockers'):
        records.append(('E2 最终失败集', data['e2']['active_blockers'], '#4C72B0'))
    if data['e3'].get('active_blockers'):
        records.append(('E3 最终失败集', data['e3']['active_blockers'], '#DD8452'))
    if not records:
        return None
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.3))
    width = 0.38
    bins = ['0', '1', '2', '3-4', '5-8', '9+']
    def _bin(value):
        if value <= 2:
            return str(value)
        if value <= 4:
            return '3-4'
        if value <= 8:
            return '5-8'
        return '9+'
    positions = range(len(bins))
    for offset, (label, blockers, color) in zip((-width / 2, width / 2), records):
        counts = Counter(_bin(int(key)) for key, value in
                         blockers['histogram'].items()
                         for _ in range(value))
        values = [counts.get(bin_name, 0) for bin_name in bins]
        bars = ax1.bar([pos + offset for pos in positions], values, width,
                       label=label, color=color)
        ax1.bar_label(bars, fontsize=7)
    ax1.set_xticks(list(positions))
    ax1.set_xticklabels(bins)
    ax1.set_xlabel('最终失败路线的有效 blocker 数')
    ax1.set_ylabel('失败路线条数')
    ax1.set_title('失败路线有效 blocker 数分布')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    sizes = [int(key) for key in next(iter(records))[1]['cumulative_ge']]
    for label, blockers, color in records:
        values = [blockers['cumulative_ge'][str(size)] for size in sizes]
        ax2.plot(sizes, values, marker='o', label=label, color=color, linewidth=2)
        for x_value, y_value in zip(sizes, values):
            ax2.annotate(str(y_value), (x_value, y_value),
                         textcoords='offset points', xytext=(0, 6),
                         ha='center', fontsize=8)
    ax2.set_xscale('log', base=2)
    ax2.set_xticks(sizes)
    ax2.set_xticklabels([str(size) for size in sizes])
    ax2.set_xlabel('拆线规模 k')
    ax2.set_ylabel('具备 ≥k 个有效 blocker 的失败路线数')
    ax2.set_title('各 k 规模的可行目标路线数（必要条件）')
    ax2.grid(alpha=0.3)
    ax2.legend()
    return _save(fig, 'fig_k_availability.png')


# ---------------------------------------------------------------------------
# markdown tables (copied into ANALYSIS_RR.md)
# ---------------------------------------------------------------------------
def _markdown_tables(data):
    lines = []
    add = lines.append
    add('### 表 A：实验总览')
    add('')
    add('| 实验 | R&R 前 routed | 最终 routed | 总增益 | 其中交易提交 | 其中分析直通 | 耗时 s | 备注 |')
    add('| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |')
    add(f"| BASE | - | {data['base']['routed']} | - | - | - | "
        f"{(data['base']['seconds'] or 0):.0f}（历史运行） | 历史 V2-C |")
    e1 = data.get('e1') or {}
    if e1.get('available'):
        add(f"| E1 | - | {e1['routed']} | +{e1['routed'] - data['base']['routed']} | "
            f"- | - | {e1['seconds']:.0f} | 扩展候选贪心顺序插入 |")
    if data['e3_phase1']['available']:
        phase1 = data['e3_phase1']
        add(f"| E3 phase1 | {data['base']['routed']} | {phase1['routed']} | "
            f"+{phase1['routed'] - data['base']['routed']} | - | - | "
            f"{phase1['seconds']:.0f} | 1600 预算顺序插入 |")
    if data['e2']['available']:
        e2 = data['e2']
        add(f"| E2 | {e2['initial_routed']} | {e2['final_routed']} | "
            f"+{e2['gain']} | +{e2.get('transaction_gain', 0)} | "
            f"+{e2.get('analysis_placements', 0)} | {e2['seconds']:.0f} | "
            f"原始候选生成器 + R&R |")
    if data['e3']['available']:
        e3 = data['e3']
        add(f"| E3 | {e3['initial_routed']} | {e3['final_routed']} | "
            f"+{e3['gain']} | +{e3.get('transaction_gain', 0)} | "
            f"+{e3.get('analysis_placements', 0)} | {e3['seconds']:.0f}（R&R） | "
            f"扩展候选 + R&R（首轮零增益早停） |")
    e3x = data.get('e3x') or {}
    if e3x.get('available'):
        add(f"| E3X（延伸） | {e3x['initial_routed']} | {e3x['final_routed']} | "
            f"+{e3x['gain']} | +{e3x.get('transaction_gain', 0)} | "
            f"+{e3x.get('analysis_placements', 0)} | {e3x['seconds']:.0f}（R&R） | "
            f"从 E3 checkpoint 续跑，min_rounds=5、k 按轮升级、128 tx/轮、"
            f"budget=800/回插600 |")
    add('')
    add('说明：`transaction_gain` = summary.history 各轮 gain 之和（R&R 交易提交）；'
        '`analysis_placements` = 总增益 − transaction_gain，即 analyse_blockers '
        '重新分析时直接布通的路线（pipeline 未把它计入 history.gain）。')
    add('')

    comparison = data.get('comparison') or {}
    per_comparison = comparison.get('per') or {}
    if per_comparison:
        add('### 表 G：各实验新增路线集合与 E1 的重叠（同一 BASE 布局）')
        add('')
        add('| 实验 | 新增路线数 | 与 E1 新增集合重叠 | 不在 E1 新增集合中 | E1 新增但该实验未布通 |')
        add('| --- | ---: | ---: | ---: | ---: |')
        for label in ('e2', 'e3', 'e3x'):
            entry = per_comparison.get(label)
            if not entry:
                continue
            add(f"| {label.upper()} | {entry['new_count']} | "
                f"{entry.get('overlap_e1_new', '-')} | "
                f"{entry.get('not_in_e1', '-')} | "
                f"{entry.get('e1_new_not_in_experiment', '-')} |")
        if comparison.get('e1_new_count') is not None:
            add('')
            add(f"E1 新增路线数 = {comparison['e1_new_count']}。")
        e3x = data.get('e3x') or {}
        if e3x.get('available'):
            add('')
            add(f"E3X 相对 E3 的净新增路线：{e3x.get('extension_new_count', 0)} 条"
                f"（{e3x.get('extension_new_route_ids') or []}）")
        add('')

    for key, label in (('e2', 'E2'), ('e3', 'E3')):
        record = data.get(key) or {}
        if not record.get('available') or not record.get('history'):
            continue
        add(f'### 表 B{label[1]}：{label} R&R 每轮记录')
        add('')
        add('| 轮 | 分析路线数 | transactions | improving | committed | 交易净增 | 分析直通 | 轮末 routed | 累计耗时 s |')
        add('| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
        for row in record['history']:
            add(f"| {row['round']} | {row.get('analysed', '-')} | {row['transactions']} | "
                f"{row['improving']} | "
                f"{row['committed']} | +{row['gain']} | "
                f"+{row.get('analysis_placements', 0)} | {row['routed']} | "
                f"{row['seconds']:.1f} |")
        add('')

    e3x = data.get('e3x') or {}
    if e3x.get('available') and e3x.get('history'):
        add('### 表 B4：E3X（R&R 延伸）每轮记录')
        add('')
        add('（从 E3 检查点续跑；`k` 为本轮使用的拆线规模——按轮升级 1→2→4→8→12；'
            '128 transactions/轮；改进机制含 extras 多路线机会插入）')
        add('')
        add('| 轮 | k | 分析路线数 | transactions | improving | committed | 交易净增 | 分析直通 | 轮末 routed | 累计耗时 s |')
        add('| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
        for row in e3x['history']:
            add(f"| {row['round']} | {row.get('k_used', '-')} | "
                f"{row.get('analysed', '-')} | {row['transactions']} | "
                f"{row['improving']} | {row['committed']} | +{row['gain']} | "
                f"+{row.get('analysis_placements', 0)} | {row['routed']} | "
                f"{row['seconds']:.1f} |")
        add('')
        if e3x.get('k_table'):
            add('### 表 I：E3X 各 k 的成交与净增（k 由轮次决定）')
            add('')
            add('| k | committed | 交易净增（含 extras +N） | 非 +1 交易数 | 成交轮次 |')
            add('| ---: | ---: | ---: | ---: | --- |')
            for row in e3x['k_table']['rows']:
                rounds = ','.join(str(value) for value in row.get('rounds') or []) or '-'
                add(f"| {row['k']} | {row['committed']} | {row['gain']} | "
                    f"{row['multi_gain']} | {rounds} |")
            add('')

    if data['k_combined']['rows']:
        add('### 表 C：拆线规模 k 的收益（E2+E3 官方臂合并）')
        add('')
        add('| k | committed 交易数（=新增布通） | 占比 | E2 | E3 | 平均 gain/交易 |')
        add('| ---: | ---: | ---: | ---: | ---: | ---: |')
        for row in data['k_combined']['rows']:
            per = {entry['label']: entry['committed'] for entry in row['experiments']}
            mean_gain = (row['gain'] / row['committed']) if row['committed'] else 0.0
            add(f"| {row['k']} | {row['committed']} | {row['share'] * 100:.1f}% | "
                f"{per.get('E2', 0)} | {per.get('E3', 0)} | {mean_gain:.2f} |")
        add('')

    for key, label in (('e2', 'E2'), ('e3', 'E3')):
        record = data.get(key) or {}
        table = record.get('k_table')
        if not record.get('available') or not table:
            continue
        add(f'### 表 F{label[1]}：{label} 各 k 的成交与最终可行目标数')
        add('')
        add('（可行目标数 = 该实验**最终**失败路线中有效 blocker 数 ≥k 的条数；'
            '仅表示 k 规模的可行上限，不是运行中各轮的实时分母）')
        add('')
        add('| k | committed | 最终可行目标数 | 每 100 个可行目标的成交数 | 成交轮次 |')
        add('| ---: | ---: | ---: | ---: | --- |')
        for row in table['rows']:
            rounds = ','.join(str(value) for value in row.get('rounds') or []) or '-'
            add(f"| {row['k']} | {row['committed']} | "
                f"{row.get('feasible_targets_final', 0)} | "
                f"{row.get('commits_per_100_feasible', 0.0):.2f} | {rounds} |")
        add('')

    replay = data.get('k_replay') or {}
    replay_titles = {'base': 'BASE 206/512（E2 参数：budget=200/回插 200）',
                     'e3phase1': 'E3 phase1 243/512（E3 参数：budget=1600/回插 800）'}
    replay_arms = (('A_fewest_blockers', 'A 组：blocker 最少的目标'),
                   ('B_most_blockers', 'B 组：blocker 最多的目标'))
    replay_layouts = replay.get('layouts') or {}
    for key in ('base', 'e3phase1'):
        layout = replay_layouts.get(key)
        if not layout:
            continue
        for arm, arm_label in replay_arms:
            rows = ((layout.get('arms_results') or {}).get(arm) or {}).get('rows') or []
            rows = [row for row in rows if row['attempted'] > 0]
            if not rows:
                continue
            add(f'### 表 H-{key}-{arm[0]}：k 受控重放 · '
                f'{replay_titles.get(key, key)} · {arm_label}')
            add('')
            add(f'（冻结布局 routed={layout.get("routed")}；执行该轮全部交易，'
                f'共 {layout.get("transactions_executed", 0)} 笔；'
                f'交易构造同官方首轮 seed；未做“顺序合并提交”，'
                f'因此度量的是**单笔交易的独立成功率**）')
            add('')
            add('| k | 尝试数 | 目标插入成功 | 全部回插成功（净 +1） | 目标插入率 | 净增益率 | 平均候选评价 | 平均耗时 s |')
            add('| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
            for row in rows:
                add(f"| {row['k']} | {row['attempted']} | {row['target_placed']} | "
                    f"{row['improving']} | {row['target_placed_rate'] * 100:.1f}% | "
                    f"{row['improving_rate'] * 100:.1f}% | {row['mean_evals']:.0f} | "
                    f"{row['mean_seconds']:.2f} |")
            add('')

    for key, label in (('e2', 'E2'), ('e3', 'E3')):
        record = data.get(key) or {}
        if not record.get('active_blockers'):
            continue
        blockers = record['active_blockers']
        cumulative = blockers['cumulative_ge']
        add(f'### 表 D{label[1]}：{label} 最终失败路线的有效 blocker 数')
        add('')
        add(f"样本 {blockers['n']} 条失败路线，平均有效 blocker 数 "
            f"{blockers['mean']:.2f}；具备 ≥k 个有效 blocker 的路线数：")
        add('')
        add('| k | ' + ' | '.join(str(size) for size in SIZES) + ' |')
        add('| ---: | ' + ' | '.join('---:' for _ in SIZES) + ' |')
        add('| 可行路线数 | ' + ' | '.join(
            str(cumulative[str(size)]) for size in SIZES) + ' |')
        add('')

    if data.get('cross_checks'):
        add('### 表 E：日志与 summary 一致性校验')
        add('')
        add('| 实验 | 日志 committed | summary committed | 日志 gain | summary gain | 一致 |')
        add('| --- | ---: | ---: | ---: | ---: | --- |')
        for check in data['cross_checks']:            add(f"| {check['label']} | {check['log_committed']} | "
                f"{check['summary_committed']} | {check['log_gain']} | "
                f"{check['summary_gain']} | "
                f"{'是' if check['consistent'] else '否'} |")
        add('')
    if data.get('warnings'):
        add('### 警告')
        add('')
        for warning in data['warnings']:
            add(f'- {warning}')
        add('')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
def _parse_cli(argv):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--k-replay', action='store_true',
                        help='run the controlled per-k transaction replay '
                             '(frozen BASE + E3 phase1 layouts, ~10-20 min)')
    parser.add_argument('--replay-plan', default='base:A48;e3phase1:A48,B16',
                        help='分布局/组的重放计划，如 base:A48;e3phase1:A48,B16')
    parser.add_argument('--replay-workers', type=int, default=8)
    return parser.parse_args(argv or [])


def main(argv=None):
    args = _parse_cli(argv)
    if args.k_replay:
        run_k_replay(plan=_parse_replay_plan(args.replay_plan),
                     workers=args.replay_workers)
    picked_fonts = _setup_matplotlib()
    print(f'CJK fonts in use: {picked_fonts}')
    data = collect()
    replay = _load_k_replay()
    if replay:
        data['k_replay'] = replay
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    figures = []
    for builder in (figure_k_scale, figure_rounds_curve,
                    figure_experiment_compare, figure_round_gain,
                    figure_k_availability, figure_phase1_progress,
                    figure_k_replay):
        try:
            path = builder(data)
        except Exception as exc:  # noqa: BLE001 - one missing arm must not stop all
            print(f'{builder.__name__}: skipped ({type(exc).__name__}: {exc})')
            continue
        if path is not None:
            figures.append(str(path))
            print(f'figure written {path}')
    data['figures'] = figures
    data_path = FIG_DIR / 'rr_analysis_data.json'
    data_path.write_text(json.dumps(data, indent=1, ensure_ascii=False),
                         encoding='utf-8')
    print(f'data written {data_path}')
    tables = _markdown_tables(data)
    tables_path = FIG_DIR / 'rr_tables.md'
    tables_path.write_text(tables, encoding='utf-8')
    print(f'tables written {tables_path}')
    print()
    print(tables)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
