"""Run: .venv/Scripts/python.exe -m four_side_1024.run [--seconds 600]."""
import argparse
import datetime
import json
import time
from pathlib import Path

from .inputs import DEFAULT_INPUT, DEFAULT_OUTPUT, config, phase1, save_json, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--seconds', type=float, default=600.)
    parser.add_argument('--finalize-checkpoint', action='store_true', help='Reaudit/export a completed search without rerunning it')
    args = parser.parse_args()
    cfg = config(); cfg['search_seconds'] = args.seconds
    start = time.perf_counter(); args.output.mkdir(parents=True, exist_ok=True)
    if args.finalize_checkpoint:
        cfg=json.loads((args.output/'config.json').read_text(encoding='utf-8'))
        previous=json.loads((args.output/'statistics.json').read_text(encoding='utf-8')) if (args.output/'statistics.json').exists() else {}
        start-=previous.get('total_runtime_seconds',0.)
    with (args.output/'run.log').open('a' if args.finalize_checkpoint else 'w', encoding='utf-8', buffering=1) as f:
        def log(message):
            text = f'{datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()} {message}'
            print(text, flush=True); f.write(text+'\n')
        if args.finalize_checkpoint:
            routes,endpoints,connectors,validation=load(args.input,cfg)
            assert (args.output/'input_connectivity.csv').read_bytes()==args.input.read_bytes()
            data=json.loads((args.output/'search_checkpoint.json').read_text(encoding='utf-8'))
            accepted={r['route_id']:r for r in data['accepted']}; failed={r['route_id']:r for r in data['failed']}
            from .outputs import finalize
            log('reaudit existing best checkpoint under unchanged search crossing policy')
            finalize(routes,endpoints,connectors,validation,accepted,failed,data['search'],cfg,args.output,start,log)
            log(f'checkpoint revalidation/export completed, accumulated execution={time.perf_counter()-start:.3f}s')
            return
        log('phase1: load original CSV and render connectivity before routing')
        routes, endpoints, connectors, validation = phase1(args.input, args.output, cfg)
        assert (args.output/'01_connectivity.png').exists()
        log(f'phase1 passed: {len(routes)} routes, {len(endpoints)} identities, sha256={validation["csv_sha256"]}')
        # Import routing only after the mandatory first visualization exists.
        from .router import route_all
        accepted, failed, search = route_all(routes, endpoints, cfg, log)
        checkpoint = dict(accepted=list(accepted.values()), failed=list(failed.values()), search=search)
        save_json(args.output/'search_checkpoint.json', checkpoint)
        log('search checkpoint saved; auditing exact final line/arc geometry')
        from .outputs import finalize
        finalize(routes, endpoints, connectors, validation, accepted, failed, search, cfg, args.output, start, log)
        log(f'complete in {time.perf_counter()-start:.3f}s')


if __name__ == '__main__':
    main()
