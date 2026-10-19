import json
from pathlib import Path
import numpy as np

p = Path('scratch/validate_final.json')
if not p.exists():
    import subprocess
    subprocess.run(['.venv\\Scripts\\python.exe', '-m', 'four_side_1024.d56.validate_d56',
                    '--routes', 'outputs/four_side_1024_d56_optimized/routes.json',
                    '--compare-exact', '--output', str(p)], check=False)
d = json.loads(p.read_text(encoding='utf-8'))
v = d['violations']
dist = np.array([x['distance_mm'] for x in v if x.get('distance_mm') is not None])
short = (0.175 - dist) * 1000.0  # micrometres
print('legacy violations:', len(v))
print('shortfall um: min %.4f median %.3f mean %.3f max %.3f' % (
    short.min(), np.median(short), short.mean(), short.max()))
for t in (0.001, 0.005, 0.01, 0.02, 0.05, 0.075, 0.1):
    print(f'  > {t*1000:6.1f} um: {int((short > t * 1000).sum())}')
print('distance min %.6f  p1 %.6f  median %.6f' % (
    dist.min(), np.quantile(dist, 0.01), np.median(dist)))
print('kinds:', {k: sum(1 for x in v if x['kind'] == k) for k in
                 ('spacing', 'overlap', 'touch', 'crossing_window_overlap')})
