"""Known-loss and angle analysis; source geometry and allocator stay unchanged."""
from pathlib import Path
import argparse,json,subprocess
from copy import deepcopy
from hashlib import sha256
from collections import Counter
from math import atan2,degrees,isfinite
from time import perf_counter
from unittest.mock import patch
from src.io import load_legacy_512_snapshot
from src.router_2d import prepare_waveguides_2d,assign_tracks_2d,TrackPolicyConfig,generate_assigned_routes_2d
from src.geometry import smooth_orthogonal_route_2d,build_special_z_smoothed_route_2d,arc_segment_radius
from src.models import LineSegment2D
from src.loss_analysis import analyze_route_loss_mm,crossing_angle_statistics,statistics


def validate(base: Path,root: Path) -> dict:
    started=perf_counter()
    output=root/"outputs"
    source=[base/"fiberBoard512.xlsx",base/"fiberBoard0data.xlsx"]
    hashes=[sha256(p.read_bytes()).hexdigest() for p in source]
    physical_summary=json.loads((output/"step_8_5_legacy_512_physical_summary.json").read_text())
    assert hashes==physical_summary["source_sha256"]
    assert physical_summary["inputs_unchanged"] and not physical_summary["errors"]
    event_path=output/"step_8_5_legacy_512_physical_events.jsonl"
    event_hash=sha256(event_path.read_bytes()).hexdigest()
    ws=load_legacy_512_snapshot(*source)
    saved_ws=deepcopy(ws)
    preps=prepare_waveguides_2d(ws,150,0)
    assignments=assign_tracks_2d(ws,preps,TrackPolicyConfig(150,.05,.125,5))
    assert Counter(a.status for a in assignments)=={"assigned":454,"unsupported_geometry":58}
    saved_assignments=deepcopy(assignments)
    special={a.waveguide_id for a in assignments if a.status=="unsupported_geometry"}
    skeletons=generate_assigned_routes_2d(ws,preps,assignments,top_y=150,bottom_y=0)
    routes=[smooth_orthogonal_route_2d(r,5) for r in skeletons]
    by_id={w.id:w for w in ws}
    routes += [build_special_z_smoothed_route_2d(i,by_id[i].start_port.position,by_id[i].end_port.position,5) for i in sorted(special)]
    saved_routes=deepcopy(routes)
    assert len(routes)==512 and len({r.waveguide_id for r in routes})==512
    with patch("src.loss.crossing_loss",side_effect=AssertionError("crossing_loss must not be called")) as forbidden:
        records=[analyze_route_loss_mm(r) for r in routes]
        events=[json.loads(line) for line in event_path.open(encoding="utf-8")]
        angles=crossing_angle_statistics(events,[r.waveguide_id for r in routes])
        assert not forbidden.called
    assert angles["degrees"]["count"]==len(events)==55935
    assert sum(h["count"] for h in angles["histogram"])==55935
    assert sum(v["physical_cross_count"] for v in angles["per_waveguide"].values())==2*55935
    for record in records:
        i=record["waveguide_id"]
        record["geometry_type"]="special" if i in special else "ordinary"
        record["allocator_status"]="unsupported_geometry" if i in special else "assigned"
        record.update(angles["per_waveguide"][i])
        assert record["total_length_mm"]>0
        for k in ("propagation_loss_db","bend_loss_db","known_non_crossing_loss_db"):
            assert isfinite(record[k]) and record[k]>=0
    keys=("line_length_mm","arc_length_mm","total_length_mm","propagation_loss_db",
          "arc_count","total_bend_angle_rad","bend_loss_db","known_non_crossing_loss_db")
    groups={}
    for name in ("ordinary","special","global"):
        selected=[r for r in records if name=="global" or r["geometry_type"]==name]
        groups[name]={k:statistics([r[k] for r in selected]) for k in keys}
    plot=[]
    xs=[]
    for r in routes:
        parts=[]
        for s in r.segments:
            xs.extend((s.start.x,s.end.x))
            if isinstance(s,LineSegment2D):
                parts.append(dict(kind="line",x1=s.start.x,y1=s.start.y,x2=s.end.x,y2=s.end.y))
            else:
                parts.append(dict(kind="arc",cx=s.center.x,cy=s.center.y,r=arc_segment_radius(s),
                    start_deg=degrees(atan2(s.start.y-s.center.y,s.start.x-s.center.x)),sweep_deg=degrees(s.sweep_rad)))
        plot.append(dict(id=r.waveguide_id,special=r.waveguide_id in special,segments=parts))
    plot_path=output/"step_8_5_legacy_512_plot_geometry.json"
    plot_path.write_text(json.dumps(dict(xmin=min(xs)-5,xmax=max(xs)+5,routes=plot)),encoding="utf-8")
    png=output/"step_8_5_legacy_512_smoothed.png"
    subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str(root/"scripts/render_legacy_512_smoothed.ps1"),
                    "-InputJson",str(plot_path),"-OutputPng",str(png)],check=True)
    assert png.read_bytes().startswith(b"\x89PNG")
    unchanged=(ws==saved_ws and assignments==saved_assignments and routes==saved_routes
               and hashes==[sha256(p.read_bytes()).hexdigest() for p in source]
               and event_hash==sha256(event_path.read_bytes()).hexdigest())
    assert unchanged
    del angles["per_waveguide"]
    summary=dict(configuration=dict(radius_mm=5,propagation_db_per_cm=.05,mm_per_cm=10,
                    bend_rule="L90(radius_mm) * abs(sweep_rad)/(pi/2)",crossing_loss="unavailable"),
                 counts=dict(analytic=512,ordinary=454,special=58,allocator_assigned=454,allocator_unsupported=58),
                 groups=groups,crossing_angles=angles,per_waveguide=sorted(records,key=lambda r:r["waveguide_id"]),
                 top_crossing_burden=sorted(records,key=lambda r:(-r["physical_cross_count"],r["waveguide_id"]))[:10],
                 inputs_unchanged=unchanged,source_hashes=hashes,physical_events_sha256=event_hash,
                 runtime_seconds=perf_counter()-started,png=str(png))
    (output/"step_8_5_legacy_512_loss_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k!="per_waveguide"},indent=2))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy_directory",type=Path)
    args=parser.parse_args()
    validate(args.legacy_directory,Path(__file__).resolve().parents[1])
