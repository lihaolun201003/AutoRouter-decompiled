"""Read-only deterministic visualization of the Step 10 analytic checkpoint."""
import json
from collections import Counter
from math import ceil, pi
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection
from matplotlib.lines import Line2D
from .fixed_1024_routing import deserialize_route3d
from .geometry_3d import (LineSegment3D, PlanarArcSegment3D, CosineTransition3D,
    PathWindowTransition3D)

COLORS={0:'#87929c',1:'#0072B2',2:'#D55E00','transition':'#713d88'}
STYLES={0:'solid',1:'solid',2:'dashed','transition':'dotted'}

def load_checkpoint(path):
    data=json.loads(path.read_text(encoding='utf-8'))
    routes={r['route_id']:deserialize_route3d(r['geometry']) for r in data['routes']}
    counts=Counter(r['target_layer'] for r in data['routes'])
    transitions=sum(isinstance(p,CosineTransition3D) for r in routes.values() for p in r.primitives)
    if len(data['routes'])!=1024 or len(routes)!=1024 or counts!={0:849,1:72,2:103} or transitions!=350:
        raise ValueError('NEEDS REVISION: Step 10 checkpoint counts differ')
    for r in routes.values():r.validate()
    return data,routes

def sample_primitive(p):
    if isinstance(p,LineSegment3D):n=2
    elif isinstance(p,PlanarArcSegment3D):n=max(12,min(65,ceil(abs(p.sweep_angle)/(pi/64))+1))
    elif isinstance(p,CosineTransition3D):n=49
    elif type(p) is PathWindowTransition3D:n=max(49,8*len(p.pieces))
    else:raise TypeError(type(p))
    return np.array([[q.x,q.y,q.z] for q in (p.point_at(float(t)) for t in np.linspace(0,1,n))])

def classify(p):
    if isinstance(p,(CosineTransition3D,PathWindowTransition3D)):return 'transition'
    z=p.point_at(0).z
    if abs(z-round(z))>1e-8 or round(z) not in (0,1,2):raise ValueError('Unexpected planar height')
    return int(round(z))

def display_points(points,scale):
    result=points.copy();result[:,2]*=scale;return result

def select_examples(data,routes):
    return {layer:min((r['route_id'] for r in data['routes'] if r['target_layer']==layer and sum(isinstance(p,CosineTransition3D) for p in routes[r['route_id']].primitives)==2),key=lambda i:(sum(p.length() for p in routes[i].primitives if classify(p)==layer),i)) for layer in (1,2)}

def generate_figures(data,routes,out):
    out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'savefig.facecolor':'white'})
    segments=[(i,classify(p),sample_primitive(p)) for i,r in sorted(routes.items()) for p in r.primitives]
    endpoints=np.array([r[k]['xyz'] for r in data['routes'] for k in ('source','destination')])
    pmts={}
    for row in data['routes']:
        for k in ('source','destination'):
            e=row[k];pmts.setdefault(e['pmt_id'],[]).append(e['xyz'])
    files=[]
    def save(fig,name):
        for ext in ('png','pdf'):
            path=out/(name+'.'+ext);fig.savefig(path,dpi=300,bbox_inches='tight');files.append(path.name)
        plt.close(fig)
    def legend(ax):
        ax.legend(handles=[Line2D([0],[0],color=COLORS[k],linestyle=STYLES[k],label=f'Layer {k}' if isinstance(k,int) else 'Transition') for k in COLORS],loc='upper left',fontsize=8)
    def frame2(ax):
        ax.plot([0,300,300,0,0],[0,0,200,200,0],color='#333333',lw=.7)
        ax.set(xlim=(-5,305),ylim=(-7,207),xlabel='x (mm)',ylabel='y (mm)');ax.set_aspect('equal')
    def draw3(ax,items,scale,local=False):
        for k in COLORS:
            arr=[display_points(a,scale) for _,c,a in items if c==k]
            if arr:ax.add_collection3d(Line3DCollection(arr,colors=COLORS[k],linewidths=1.9 if local else (.23 if k==0 else .7),alpha=1 if local else (.2 if k==0 else .8),linestyles=STYLES[k]),autolim=False)
        ax.set(xlabel='x (mm)',ylabel='y (mm)',zlabel='z (mm; true values)')
        ax.set_zticks([0,scale,2*scale],['0','1','2']);ax.view_init(elev=24,azim=-62)
    for scale,suffix in ((1,'overview'),(20,'overview_z20')):
        fig=plt.figure(figsize=(11,7));ax=fig.add_subplot(projection='3d')
        draw3(ax,segments,scale)
        ax.plot([0,300,300,0,0],[0,0,200,200,0],[0]*5,color='#333333',lw=.7)
        ax.scatter(*endpoints.T,s=1,c='#333333',alpha=.4)
        ax.set(xlim=(0,300),ylim=(0,200),zlim=(0,2*scale));ax.set_box_aspect((300,200,2*scale))
        ax.set_title('Fixed 1024-Channel 3D Optical Waveguide Routing\n'+('True geometric scale' if scale==1 else 'Z visual exaggeration ×20; true layers 0 / 1 / 2 mm'))
        legend(ax);save(fig,'step_11_1024_3d_'+suffix)
    for layer in (0,1,2):
        fig,ax=plt.subplots(figsize=(10,7));arr=[a[:,:2] for _,c,a in segments if c==layer]
        ax.add_collection(LineCollection(arr,colors=COLORS[layer],linewidths=.25 if layer==0 else .7,alpha=.45 if layer==0 else .85,linestyles=STYLES[layer]))
        frame2(ax);ax.set_title(f'Layer {layer}: actual planar sections at z = {layer} mm')
        save(fig,f'step_11_layer_{layer}')
    fig,ax=plt.subplots(figsize=(10,7))
    for k in COLORS:
        ax.add_collection(LineCollection([a[:,:2] for _,c,a in segments if c==k],colors=COLORS[k],linewidths=.25 if k==0 else .65,alpha=.22 if k==0 else .8,linestyles=STYLES[k]))
    ax.scatter(endpoints[:,0],endpoints[:,1],s=2,color='#333333')
    for pts in pmts.values():
        a=np.array(pts);ax.plot([a[:,0].min(),a[:,0].max()],[a[0,1]]*2,color='black',lw=1.4)
    frame2(ax);legend(ax);ax.set_title('All 1024 routes: XY projection; PMTs and endpoints on board edges')
    save(fig,'step_11_1024_xy_projection')
    examples=select_examples(data,routes)
    for layer,rid in examples.items():
        primitives=routes[rid].primitives
        idx=[j for j,p in enumerate(primitives) if isinstance(p,CosineTransition3D)]
        items=[(rid,classify(p),sample_primitive(p)) for p in primitives[max(0,idx[0]-1):idx[-1]+2]]
        # Keep both complete transitions and high section; trim only display of long low-layer tails.
        for n in (0,len(items)-1):
            i,c,a=items[n]
            if c==0 and len(a)==2:
                length=np.linalg.norm(a[1]-a[0]);fraction=min(1,10/max(length,1e-9))
                a=a.copy()
                if n==0:a[0]=a[1]+fraction*(a[0]-a[1])
                else:a[1]=a[0]+fraction*(a[1]-a[0])
                items[n]=(i,c,a)
        cloud=np.concatenate([a for _,_,a in items]);lo=cloud.min(axis=0);hi=cloud.max(axis=0)
        fig=plt.figure(figsize=(11,7));ax=fig.add_subplot(projection='3d');draw3(ax,items,20,True)
        ax.set(xlim=(lo[0]-2,hi[0]+2),ylim=(lo[1]-2,hi[1]+2),zlim=(0,layer*20+3));ax.set_box_aspect((max(hi[0]-lo[0],8),max(hi[1]-lo[1],8),layer*20))
        for j,label in zip(idx,('Rise','Fall')):
            q=primitives[j].point_at(.5);ax.text(q.x,q.y,q.z*20,label,fontsize=9)
        ax.set_title(f'Layer {layer} Elevation Example — Route {rid}\nZ visual exaggeration ×20; low-layer tails cropped for display')
        legend(ax);save(fig,f'step_11_layer{layer}_elevation_example')
        fig,ax=plt.subplots(figsize=(10,3.5))
        # Distance along the transition direction avoids collapsed Y-directed transitions in XZ.
        direction=np.array([primitives[idx[0]].point_at(1).x-primitives[idx[0]].point_at(0).x,primitives[idx[0]].point_at(1).y-primitives[idx[0]].point_at(0).y]);direction/=np.linalg.norm(direction)
        for _,c,a in items:ax.plot(a[:,:2]@direction,a[:,2],color=COLORS[c],ls=STYLES[c],lw=2)
        ax.set(xlabel='Coordinate along transition direction (mm)',ylabel='z (mm)',yticks=[0,1,2],ylim=(-.12,2.2),title=f'Route {rid}: elevation side profile (vertical aspect enlarged)');ax.grid(alpha=.15)
        save(fig,f'step_11_layer{layer}_elevation_side')
    fig,ax=plt.subplots(figsize=(11,4))
    for k in COLORS:ax.add_collection(LineCollection([a[:,[0,2]] for _,c,a in segments if c==k],colors=COLORS[k],linewidths=.3 if k==0 else .5,alpha=.2 if k==0 else .5,linestyles=STYLES[k]))
    ax.set(xlim=(0,300),ylim=(-.1,2.15),yticks=[0,1,2],xlabel='x (mm)',ylabel='z (mm)',title='All 1024 routes: XZ projection (vertical aspect enlarged)');legend(ax)
    save(fig,'step_11_1024_xz_side')
    for name,labels,values,colors,title in (
        ('layer_usage_bar',['Layer 0','Layer 1','Layer 2'],[849,72,103],[COLORS[i] for i in range(3)],'Route states by maximum layer (not planar section counts)'),
        ('collision_reduction_bar',['Initial','Final'],[204291,138113],['#87929c','#0072B2'],'Collision pairs: saved Step 10 results; reduction 32.394%')):
        fig,ax=plt.subplots(figsize=(8,4.5));bars=ax.bar(labels,values,color=colors,width=.55);ax.bar_label(bars,labels=[f'{v:,}' for v in values],padding=4);ax.set_ylim(0,max(values)*1.18);ax.set_title(title);ax.set_ylabel('Routes' if name.startswith('layer') else 'Collision pairs');save(fig,'step_11_'+name)
    return dict(files=files,figure_count=len(files)//2,examples=examples,sampled_points=sum(len(a) for _,_,a in segments),planar_section_counts={str(k):sum(c==k for _,c,_ in segments) for k in (0,1,2)})
