"""Read-only HD/vector rendering of the saved analytic plotting geometry."""
from pathlib import Path
from math import cos,sin,radians,ceil
from hashlib import sha256
import json,subprocess,struct
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs"
PREFIX="step_8_5_legacy_512_smoothed"
def digest(p):
    return sha256(p.read_bytes()).hexdigest()

def main():
    protected=[p for folder in ("src","outputs") for p in (ROOT/folder).rglob("*")
               if p.is_file() and p.name not in (PREFIX+".svg",PREFIX+"_special_highlight.svg",PREFIX+"_hd.png")]
    before={str(p):digest(p) for p in protected}
    source=OUT/"step_8_5_legacy_512_plot_geometry.json"
    data=json.loads(source.read_text())
    routes=data["routes"]
    assert len(routes)==len({r["id"] for r in routes})==512
    assert sum(r["special"] for r in routes)==58
    # Check analytic endpoints and every contained cardinal extremum, not just
    # endpoint bounds, before using the existing 0..150 plot extent.
    for route in routes:
        for s in route["segments"]:
            if s["kind"]=="line":
                points=[(s["x1"],s["y1"]),(s["x2"],s["y2"])]
            else:
                start,sweep=s["start_deg"],s["sweep_deg"]
                angles=[start,start+sweep]
                for a in (0,90,180,270):
                    delta=((a-start) if sweep>0 else (start-a))%360
                    if delta<=abs(sweep)+1e-10: angles.append(a)
                points=[(s["cx"]+s["r"]*cos(radians(a)),s["cy"]+s["r"]*sin(radians(a))) for a in angles]
            assert all(data["xmin"]<=x<=data["xmax"] and -1e-9<=y<=150+1e-9 for x,y in points)
    scale=min(940/(data["xmax"]-data["xmin"]),800/150)
    def xy(x,y):
        return 90+(x-data["xmin"])*scale,890-y*scale
    def svg(highlight=False):
        parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="1000" viewBox="0 0 1100 1000">',
               '<rect width="1100" height="1000" fill="white"/>',
               '<g font-family="Arial,sans-serif" fill="#202830">',
               '<text x="90" y="36" font-size="24">Legacy 512 Smoothed Routes</text>',
               '<text x="90" y="65" font-size="16">Blue: ordinary (454)   Orange: special-Z (58)</text></g>']
        for r in routes:
            color="#df601a" if r["special"] else "#235fb4"
            opacity=0.95 if r["special"] else (0.15 if highlight else 0.55)
            width=1.25 if r["special"] else 0.65
            parts.append(f'<g id="route-{r["id"]}" data-special="{str(r["special"]).lower()}" fill="none" stroke="{color}" stroke-opacity="{opacity}" stroke-width="{width}">')
            for s in r["segments"]:
                if s["kind"]=="line":
                    x1,y1=xy(s["x1"],s["y1"]);x2,y2=xy(s["x2"],s["y2"])
                    parts.append(f'<path d="M {x1:.12g} {y1:.12g} L {x2:.12g} {y2:.12g}"/>')
                else:
                    a,b=radians(s["start_deg"]),radians(s["start_deg"]+s["sweep_deg"])
                    x1,y1=xy(s["cx"]+s["r"]*cos(a),s["cy"]+s["r"]*sin(a))
                    x2,y2=xy(s["cx"]+s["r"]*cos(b),s["cy"]+s["r"]*sin(b))
                    radius=s["r"]*scale
                    large=int(abs(s["sweep_deg"])>180)
                    sweep=int(s["sweep_deg"]<0) # screen y points downward
                    parts.append(f'<path d="M {x1:.12g} {y1:.12g} A {radius:.12g} {radius:.12g} 0 {large} {sweep} {x2:.12g} {y2:.12g}"/>')
            parts.append('</g>')
        parts.append(f'<rect x="90" y="90" width="{(data["xmax"]-data["xmin"])*scale}" height="800" fill="none" stroke="#889099" stroke-width="0.7"/>')
        parts.append('<g font-family="Arial,sans-serif" font-size="16" fill="#202830">')
        for y in range(0,151,25):
            parts.append(f'<text x="72" y="{890-y*scale+5}" text-anchor="end">{y}</text>')
        for x in range(ceil(data["xmin"]/50)*50,int(data["xmax"])+1,50):
            parts.append(f'<text x="{xy(x,0)[0]}" y="920" text-anchor="middle">{x}</text>')
        parts.extend(['<text x="950" y="920">X (mm)</text>','<text x="12" y="115">Y (mm)</text>','</g></svg>'])
        return "\n".join(parts)
    for suffix,highlight in ((".svg",False),("_special_highlight.svg",True)):
        p=OUT/(PREFIX+suffix)
        p.write_text(svg(highlight),encoding="utf-8")
        tree=ET.parse(p)
        ns={"s":"http://www.w3.org/2000/svg"}
        assert not tree.findall(".//s:image",ns)
        assert len([g for g in tree.findall(".//s:g",ns) if g.get("id","").startswith("route-")])==512
        paths=tree.findall(".//s:path",ns)
        assert len(paths)==sum(len(r["segments"]) for r in routes)
        assert sum(" A " in p.get("d","") for p in paths)==1024
    ps=(ROOT/"scripts/render_legacy_512_smoothed.ps1").read_text()
    ps=ps.replace("Bitmap 1100,1000","Bitmap 8000,7273")
    ps=ps.replace("$g.Clear([System.Drawing.Color]::White)",
        "$g.PixelOffsetMode=[System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality\n"
        "$g.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic\n"
        "$g.CompositingQuality=[System.Drawing.Drawing2D.CompositingQuality]::HighQuality\n"
        "$g.ScaleTransform([single](8000.0/1100.0),[single](8000.0/1100.0))\n"
        "$g.Clear([System.Drawing.Color]::White)")
    ps=ps.replace("85,35,95,180","140,35,95,180").replace("170,225,95,20","242,225,95,20")
    ps=ps.replace(")),0.8",")),0.65")
    ps=ps.replace("Legacy 512 analytic centerlines | equal x/y scale | mm","Legacy 512 Smoothed Routes")
    ps=ps.replace("Blue: 454 ordinary | Orange: 58 independent special-Z (allocator unsupported)","Blue: ordinary (454) | Orange: special-Z (58)")
    ps="\n".join(line for line in ps.splitlines() if "Zero-width geometry;" not in line)
    renderer=ROOT/"scripts/render_legacy_512_smoothed_hd.ps1"
    renderer.write_text(ps,encoding="utf-8")
    png=OUT/(PREFIX+"_hd.png")
    subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str(renderer),
                    "-InputJson",str(source),"-OutputPng",str(png)],check=True)
    raw=png.read_bytes()
    assert raw[:8]==b"\x89PNG\r\n\x1a\n"
    size=struct.unpack(">II",raw[16:24])
    assert max(size)>=6000
    assert before=={str(p):digest(p) for p in protected}
    print(json.dumps(dict(routes=512,ordinary=454,special=58,png_pixels=size,inputs_unchanged=True,
        files={suffix:(OUT/(PREFIX+suffix)).stat().st_size for suffix in
        (".svg","_special_highlight.svg","_hd.png")}),indent=2))

if __name__=="__main__":
    main()
