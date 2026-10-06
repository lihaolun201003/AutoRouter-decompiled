"""Step 15 visualization: read-only figures from saved A/B/C experiment outputs.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\visualize_3d_strategy_v2.py PROJECT OUTDIR

Only reads outputs/3d_strategy_v2/<run>/; never reruns routing.
"""
import sys,json,csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection

ROOT=Path(sys.argv[1]).resolve();OUT=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts/publication'))
import pubstyle
from src.models import Layer,Point3D
from src.geometry_3d import lift_smoothed_route_to_layer,LineSegment3D,PlanarArcSegment3D,CosineTransition3D
from src.multi_attribution import deserialize_plot
from src.fixed_1024_routing import (legacy_waveguides_from_seed,generate_fixed_1024_input,
    build_fixed_1024_geometry,deserialize_route3d)
from src.layer_assignment_3d import build_elevation_candidate
from src.clearance_3d import analyze_route3d_clearance
from src.collision import find_smoothed_route_intersections_2d

FIG=OUT/'figures';FIG.mkdir(parents=True,exist_ok=True)
COLORS={'A':pubstyle.PALETTE['gray'],'B':pubstyle.PALETTE['blue'],'C':pubstyle.PALETTE['vermillion']}
LAYER_COLORS={0:'#87929c',1:'#0072B2',2:'#D55E00','transition':'#713d88'}
SIZES=(512,1024)
files=[]

def runs(size):return OUT/f'{size}_three_layer_abc'

def available_sizes():
    return [size for size in SIZES if (runs(size)/'summary.json').is_file()]

def load_curves(size):
    return {s:json.loads((runs(size)/f'curve_{s}.json').read_text()) for s in 'ABC'}

def load_comparison(size):
    with (runs(size)/'comparison.csv').open(encoding='utf-8-sig',newline='') as f:
        return {row['strategy']:row for row in csv.DictReader(f)}

def load_final(size,strategy):
    data=json.loads((runs(size)/f'final_routes_{strategy}.json').read_text())
    return {row['route_id']:deserialize_route3d(row['geometry']) for row in data['routes']}

def load_decisions(size,strategy):
    return json.loads((runs(size)/f'decisions_{strategy}.json').read_text())

def load_planar(size):
    if size==512:
        plotpath=ROOT/'outputs/step_8_5_legacy_512_plot_geometry.json'
        planar={r['id']:lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0))
            for r in json.loads(plotpath.read_text())['routes']}
        eventpath=ROOT/'outputs/step_8_5_legacy_512_physical_events.jsonl'
        crossings={}
        for text in eventpath.read_text().splitlines():
            e=json.loads(text)
            if e['kind']=='cross':
                crossings.setdefault(tuple(sorted((e['route_a_id'],e['route_b_id']))),[]).append(
                    Point3D(e['point']['x'],e['point']['y'],0))
        return planar,crossings
    seed=json.loads((ROOT/'data/fixed_1024_legacy_seed.json').read_text())
    planar2d,routes,_=build_fixed_1024_geometry(generate_fixed_1024_input(legacy_waveguides_from_seed(seed)))
    class Anchors:
        def get(self,pair):
            return [Point3D(e.point.x,e.point.y,0.)
                for e in find_smoothed_route_intersections_2d(planar2d[pair[0]],planar2d[pair[1]])
                if e.kind=='cross' and e.point is not None]
    return routes,Anchors()

def sample(p,n=None):
    if isinstance(p,LineSegment3D):n=n or 2
    elif isinstance(p,PlanarArcSegment3D):n=n or max(12,min(65,int(abs(p.sweep_angle)/(np.pi/64))+1))
    else:n=n or 49
    return np.array([[q.x,q.y,q.z] for q in (p.point_at(float(t)) for t in np.linspace(0,1,n))])

def classify(p):
    if isinstance(p,CosineTransition3D):return 'transition'
    z=p.point_at(0).z
    return int(round(z))


def figure_pairs_vs_evaluations():
    sizes=available_sizes()
    fig,axes=plt.subplots(1,len(sizes),figsize=(5.6*len(sizes),3.9),squeeze=False)
    for ax,size in zip(axes[0],sizes):
        curves=load_curves(size)
        budget=json.loads((runs(size)/'config.json').read_text())['frozen_budget']['candidate_budget']
        for strategy in 'ABC':
            curve=curves[strategy]
            x=[p['candidate_evaluations'] for p in curve];y=[p['collision_pair_count'] for p in curve]
            ax.plot(x,y,color=COLORS[strategy],lw=1.3,label=strategy)
        same_bc=len(curves['B'])==len(curves['C']) and all(
            a['collision_pair_count']==b['collision_pair_count'] and
            a['candidate_evaluations']==b['candidate_evaluations']
            for a,b in zip(curves['B'],curves['C']))
        if same_bc:
            ax.annotate('B 与 C 完全重合\n（该预算内没有触发重定位的机会）',
                xy=(.03,.06),xycoords='axes fraction',fontsize=8,
                bbox=dict(boxstyle='round',fc='white',ec='#888888',lw=.6))
        ax.set_xlabel('累计候选评价次数（evaluate_elevation 调用）')
        ax.set_ylabel('中心线近距对数（0.1 mm 阈值）')
        ax.set_title(f'{size} 条连接 · 三层 · 预算 {budget:,} 次候选评价')
        ax.legend(title='策略',loc='upper right')
        ax.grid(alpha=.2)
    fig.tight_layout()
    for ext in ('png','pdf'):
        fig.savefig(FIG/f'f81_pairs_vs_evaluations.{ext}',dpi=300,bbox_inches='tight');files.append(f'f81_pairs_vs_evaluations.{ext}')
    plt.close(fig)


def figure_final_comparison():
    sizes=available_sizes()
    panels=[('final_collision_pairs','终态近距对数','对'),
            ('final_extra_length_mm','终态额外长度（相对原二维总长）','mm'),
            ('runtime_seconds','运行时间（单次实测）','s'),
            ('candidate_evaluations','实际候选评价次数','次')]
    fig,axes=plt.subplots(1,4,figsize=(12,3.6))
    for ax,(key,label,unit) in zip(axes,panels):
        positions=[];heights=[];colors=[]
        for size_index,size in enumerate(sizes):
            comparison=load_comparison(size)
            for strategy_index,strategy in enumerate('ABC'):
                positions.append(size_index*4+strategy_index)
                heights.append(float(comparison[strategy][key]))
                colors.append(COLORS[strategy])
        bars=ax.bar(positions,heights,color=colors,width=.8)
        ax.set_xticks([2*size_index+1 for size_index in range(len(sizes))])
        ax.set_xticklabels([f'{s} 条' for s in sizes])
        ax.set_ylabel(f'{label}（{unit}）' if unit else label)
        ax.set_title(label)
        ax.bar_label(bars,fmt=lambda v:f'{v:,.0f}' if abs(v)>=100 else f'{v:.2f}',fontsize=7,padding=2)
        ax.set_ylim(0,max(heights)*1.22)
        ax.grid(alpha=.2,axis='y')
    handles=[Line2D([0],[0],color=COLORS[s],lw=6,label=s) for s in 'ABC']
    fig.legend(handles=handles,ncol=3,loc='lower center',frameon=False,bbox_to_anchor=(.5,-.02))
    fig.tight_layout(rect=(0,.04,1,1))
    for ext in ('png','pdf'):
        fig.savefig(FIG/f'f82_final_comparison.{ext}',dpi=300,bbox_inches='tight');files.append(f'f82_final_comparison.{ext}')
    plt.close(fig)


def _relocation_example(size):
    steps=load_decisions(size,'C')
    accepted=[s for s in steps if s['status'] in ('ELEVATED','RELOCATED')]
    by_route={}
    for s in accepted:by_route.setdefault(s['moved_route_id'],[]).append(s)
    candidates=[(len(v),r) for r,v in by_route.items() if any(s['status']=='RELOCATED' for s in v)]
    if not candidates:return None
    _,rid=max(candidates)
    route_steps=by_route[rid]
    first=next(s for s in route_steps if s['status']=='ELEVATED')
    return rid,first,route_steps


def figure_relocation_before_after():
    for size in available_sizes():
        example=_relocation_example(size)
        if example is None:continue
        rid,first,route_steps=example
        planar,crossings=load_planar(size)
        config=None
        from src.three_layer_assignment_3d import LayerConfiguration
        config=LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],.1,5.,
            'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
        anchors=crossings.get(tuple(first['target_pair']))
        if not anchors:
            report=analyze_route3d_clearance(planar[first['target_pair'][0]],planar[first['target_pair'][1]],.1)
            anchors=[Point3D(r['closest_point_a']['x'],r['closest_point_a']['y'],0.)
                for r in report['pair_results'] if r['status']=='COLLISION' and r.get('closest_point_a')]
        before=build_elevation_candidate(planar[rid],tuple(first['target_pair']),anchors,config,
            tuple(first['rise_window']),tuple(first['fall_window']),target_layer_id=first['target_layer_id'])
        final=load_final(size,'C')[rid]
        before_segments=[(classify(p),sample(p)) for p in before.route.primitives]
        after_segments=[(classify(p),sample(p)) for p in final.primitives]
        xz=[]
        for label,segments in (('before',before_segments),('after',after_segments)):
            rows=[p for _,p in segments]
            cloud=np.concatenate(rows);direction=np.array([1.,0.])
            xz.append((label,cloud))
        lo=min(c[:,0].min() for _,c in xz);hi=max(c[:,0].max() for _,c in xz)
        fig,axes=plt.subplots(2,1,figsize=(9,5.4),gridspec_kw={'height_ratios':[1.15,1]})
        ax=axes[0]
        for label,segments in (('重定位前（第一次抬升到 Layer 1）',before_segments),('重定位后（终态，Layer 2）',after_segments)):
            for kind,pts in segments:
                ax.plot(pts[:,0],pts[:,1],color=LAYER_COLORS[kind],
                    ls=':' if kind=='transition' else '-',lw=1.6 if kind=='transition' else 1.2,alpha=.95)
        ax.set_title(f'路线 {rid} 重定位前后 XY 投影（同一投影，仅高度与窗口改变）')
        ax.set_xlabel('x (mm)');ax.set_ylabel('y (mm)');ax.grid(alpha=.2)
        ax=axes[1]
        for label,segments in (('重定位前（Layer 1）',before_segments),('重定位后（Layer 2）',after_segments)):
            for kind,pts in segments:
                ax.plot(pts[:,0],pts[:,2],color=LAYER_COLORS[kind],
                    ls=':' if kind=='transition' else '-',lw=1.6 if kind=='transition' else 1.2,alpha=.95,
                    label=label if kind!='transition' else None)
        ax.set_xlabel('x (mm)');ax.set_ylabel('z (mm，真实值 0/1/2)');ax.set_yticks([0,1,2]);ax.grid(alpha=.2)
        handles=[Line2D([0],[0],color=LAYER_COLORS[k],lw=2,label=n) for k,n in
            ((1,'Layer 1 段'),(2,'Layer 2 段'),('transition','过渡段'))]
        handles+=[Line2D([0],[0],color='#333333',lw=1.2,label='重定位前'),Line2D([0],[0],color='#333333',lw=1.2,ls=':',label='过渡段')]
        ax.legend(handles=handles,loc='upper right',ncol=2,fontsize=8)
        fig.tight_layout()
        for ext in ('png','pdf'):
            fig.savefig(FIG/f'f83_relocation_route{rid}_{size}.{ext}',dpi=300,bbox_inches='tight')
            files.append(f'f83_relocation_route{rid}_{size}.{ext}')
        plt.close(fig)


def figure_3d_overview(size=1024,strategy='C'):
    if size not in available_sizes():size=available_sizes()[-1]
    routes=load_final(size,strategy)
    segments=[(classify(p),sample(p)) for _,r in sorted(routes.items()) for p in r.primitives]
    # Board frame from the actual data extent, not a fixed 1024 board guess.
    cloud=np.concatenate([p for _,p in segments])
    x0,x1=cloud[:,0].min(),cloud[:,0].max();y0,y1=cloud[:,1].min(),cloud[:,1].max()
    pad_x,pad_y=.03*(x1-x0),.03*(y1-y0)
    x0,x1,y0,y1=x0-pad_x,x1+pad_x,y0-pad_y,y1+pad_y
    for scale,suffix in ((1,'true'),(20,'z20')):
        fig=plt.figure(figsize=(10.5,6.4));ax=fig.add_subplot(projection='3d')
        for kind in (0,1,2,'transition'):
            arrays=[]
            for k,pts in segments:
                if k==kind:
                    q=pts.copy();q[:,2]*=scale;arrays.append(q)
            if not arrays:continue
            ax.add_collection3d(_line3d(arrays,LAYER_COLORS[kind],1.9 if kind=='transition' else .6),autolim=False)
        ax.plot([x0,x1,x1,x0,x0],[y0,y0,y1,y1,y0],[0]*5,color='#333333',lw=.7)
        ax.set(xlabel='x (mm)',ylabel='y (mm)',zlabel='z (mm)')
        ax.set_zticks([0,scale,2*scale],['0','1','2'])
        ax.view_init(elev=24,azim=-62)
        ax.set(xlim=(x0,x1),ylim=(y0,y1),zlim=(0,2*scale))
        ax.set_box_aspect((x1-x0,y1-y0,2*scale*.6))
        title=f'{size} 条连接 · 策略 {strategy} 终态三维总览'
        ax.set_title(title+('\n真实高度（0/1/2 mm）' if scale==1 else '\n高度放大 20 倍显示；真实层高仍为 0/1/2 mm'))
        handles=[Line2D([0],[0],color=LAYER_COLORS[k],lw=2,label=('Layer 0' if k==0 else f'Layer {k}' if isinstance(k,int) else '过渡段')) for k in (0,1,2,'transition')]
        ax.legend(handles=handles,loc='upper left',fontsize=8)
        for ext in ('png','pdf'):
            fig.savefig(FIG/f'f84_overview3d_{suffix}.{ext}',dpi=300,bbox_inches='tight');files.append(f'f84_overview3d_{suffix}.{ext}')
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4.2))
    for kind in (0,1,2,'transition'):
        arrays=[pts[:,[0,2]] for k,pts in segments if k==kind]
        if arrays:ax.add_collection(LineCollection(arrays,colors=LAYER_COLORS[kind],
            linewidths=.35 if kind==0 else .6,alpha=.22 if kind==0 else .6,
            linestyles=':' if kind=='transition' else '-'))
    ax.set(xlim=(x0,x1),ylim=(-.12,2.2),yticks=[0,1,2],xlabel='x (mm)',ylabel='z (mm，真实值)',
        title=f'{size} 条连接 · 策略 {strategy} 终态 XZ 侧视（纵向放大显示）')
    handles=[Line2D([0],[0],color=LAYER_COLORS[k],lw=2,label=('Layer 0' if k==0 else f'Layer {k}' if isinstance(k,int) else '过渡段')) for k in (0,1,2,'transition')]
    ax.legend(handles=handles,loc='upper right',fontsize=8);ax.grid(alpha=.2)
    fig.tight_layout()
    for ext in ('png','pdf'):
        fig.savefig(FIG/f'f85_xz_side.{ext}',dpi=300,bbox_inches='tight');files.append(f'f85_xz_side.{ext}')
    plt.close(fig)


def _line3d(arrays,color,lw):
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    return Line3DCollection(arrays,colors=color,linewidths=lw,alpha=.85)


def main():
    figure_pairs_vs_evaluations()
    figure_final_comparison()
    figure_relocation_before_after()
    figure_3d_overview()
    summary=dict(files=files,figure_count=len({f.rsplit('.',1)[0] for f in files}))
    (OUT/'visualization_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
