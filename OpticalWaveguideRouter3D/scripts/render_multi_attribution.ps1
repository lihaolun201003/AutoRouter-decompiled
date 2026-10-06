param([string]$ProjectPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$out = Join-Path $ProjectPath 'outputs'
$summary = Get-Content -LiteralPath (Join-Path $out 'step_8_5_m1_5_multi_attribution_summary.json') -Raw | ConvertFrom-Json
$plot = Get-Content -LiteralPath (Join-Path $out 'step_8_5_legacy_512_plot_geometry.json') -Raw | ConvertFrom-Json
$routes = @{}
foreach($route in $plot.routes){$routes[[string]$route.id]=$route}
$font = New-Object System.Drawing.Font('Arial',10)
$titleFont = New-Object System.Drawing.Font('Arial',15)
$colors = @([Drawing.ColorTranslator]::FromHtml('#1f77b4'),[Drawing.ColorTranslator]::FromHtml('#ff7f0e'),[Drawing.ColorTranslator]::FromHtml('#2ca02c'))
function Graphics-For($bitmap){
 $graphics=[Drawing.Graphics]::FromImage($bitmap)
 $graphics.SmoothingMode=[Drawing.Drawing2D.SmoothingMode]::AntiAlias
 $graphics.PixelOffsetMode=[Drawing.Drawing2D.PixelOffsetMode]::HighQuality
 $graphics.Clear([Drawing.Color]::White)
 return $graphics
}
$bmp=New-Object Drawing.Bitmap(950,950)
$g=Graphics-For $bmp
$g.DrawString('Ascending baseline: 318 exact multi centroids',$titleFont,[Drawing.Brushes]::Black,45,15)
foreach($v in (0,25,50,75,100,125,150)){
 $x=85+$v*5.3; $y=860-$v*5.3
 $g.DrawLine([Drawing.Pens]::LightGray,[single]$x,65,[single]$x,860)
 $g.DrawLine([Drawing.Pens]::LightGray,85,[single]$y,880,[single]$y)
 $g.DrawString([string]$v,$font,[Drawing.Brushes]::Black,[single]($x-8),866)
 $g.DrawString([string]$v,$font,[Drawing.Brushes]::Black,51,[single]($y-7))
}
$labels=@('special_related','top_U_related','bottom_U_related','cross_side_Z')
$palette=@('#ff7f0e','#1f77b4','#2ca02c','#9467bd')
foreach($p in $summary.centroids){
 $color=[Drawing.ColorTranslator]::FromHtml($palette[[array]::IndexOf($labels,[string]$p.group)])
 $brush=New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(155,$color))
 $g.FillEllipse($brush,[single](85+$p.x*5.3-3.1),[single](860-$p.y*5.3-3.1),6.2,6.2)
 $brush.Dispose()
}
for($i=0;$i -lt 4;$i++){
 $brush=New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml($palette[$i]))
 $g.FillEllipse($brush,85+$i*215,911,8,8)
 $g.DrawString($labels[$i],$font,[Drawing.Brushes]::Black,97+$i*215,908)
 $brush.Dispose()
}
$g.DrawString('X (mm)',$font,[Drawing.Brushes]::Black,872,889)
$g.DrawString('Y (mm)',$font,[Drawing.Brushes]::Black,10,45)
$bmp.Save((Join-Path $out 'step_8_5_m1_5_multi_centroids.png'),[Drawing.Imaging.ImageFormat]::Png)
$g.Dispose();$bmp.Dispose()
foreach($case in $summary.case_studies){
 $rec=$case.record; $cx=[double]$rec.centroid.x; $cy=[double]$rec.centroid.y
 $halfDetail=.16
 foreach($c in $rec.crosses){$halfDetail=[Math]::Max($halfDetail,[Math]::Max([Math]::Abs($c.x-$cx),[Math]::Abs($c.y-$cy))*1.5)}
 $bmp=New-Object Drawing.Bitmap(1200,660);$g=Graphics-For $bmp
 $title=$rec.multi_id+': routes '+($rec.route_ids -join ',')+' / '+$rec.paper.label
 $g.DrawString($title,$titleFont,[Drawing.Brushes]::Black,45,12)
 for($panel=0;$panel -lt 2;$panel++){
  $half=6.;if($panel -eq 1){$half=$halfDetail}
  $left=65+$panel*590; $top=95; $size=490; $scale=$size/(2*$half)
  $state=$g.Save();$g.SetClip((New-Object Drawing.RectangleF($left,$top,$size,$size)))
  $n=0
  foreach($rid in $rec.route_ids){
   $pen=New-Object Drawing.Pen($colors[$n],1.6)
   foreach($seg in $routes[[string]$rid].segments){
    if($seg.kind -eq 'line'){
     $g.DrawLine($pen,[single]($left+($seg.x1-$cx+$half)*$scale),[single]($top+($cy+$half-$seg.y1)*$scale),[single]($left+($seg.x2-$cx+$half)*$scale),[single]($top+($cy+$half-$seg.y2)*$scale))
    } else {
     $g.DrawArc($pen,[single]($left+($seg.cx-$seg.r-$cx+$half)*$scale),[single]($top+($cy+$half-$seg.cy-$seg.r)*$scale),[single](2*$seg.r*$scale),[single](2*$seg.r*$scale),[single](-$seg.start_deg),[single](-$seg.sweep_deg))
    }
   }
   $pen.Dispose();$n++
  }
  $points=@()
  foreach($c in $rec.crosses){$points+=New-Object Drawing.PointF([single]($left+($c.x-$cx+$half)*$scale),[single]($top+($cy+$half-$c.y)*$scale))}
  $pen=New-Object Drawing.Pen([Drawing.Color]::Black,1)
  $pen.DashStyle=[Drawing.Drawing2D.DashStyle]::Dash
  $g.DrawPolygon($pen,[Drawing.PointF[]]$points);$pen.Dispose()
  for($i=0;$i -lt 3;$i++){
   $g.FillEllipse([Drawing.Brushes]::Black,$points[$i].X-3,$points[$i].Y-3,6,6)
   if($panel -eq 1){$g.DrawString(@('AB','AC','BC')[$i],$font,[Drawing.Brushes]::Black,$points[$i].X+6,$points[$i].Y-17)}
  }
  $g.Restore($state)
  $g.DrawRectangle([Drawing.Pens]::Gray,$left,$top,$size,$size)
  $label='Bend context';if($panel -eq 1){$label='Triangle detail'}
  $g.DrawString($label+'; equal x/y scale; mm',$font,[Drawing.Brushes]::Black,$left,65)
  $g.DrawString(('X: {0:F6} .. {1:F6}; Y: {2:F6} .. {3:F6}' -f ($cx-$half),($cx+$half),($cy-$half),($cy+$half)),$font,[Drawing.Brushes]::Black,$left,600)
 }
 for($i=0;$i -lt 3;$i++){
  $brush=New-Object Drawing.SolidBrush($colors[$i])
  $g.DrawString(('route '+$rec.route_ids[$i]),$font,$brush,70+$i*370,631);$brush.Dispose()
 }
 $dest=Join-Path $out ([IO.Path]::GetFileNameWithoutExtension($case.svg)+'.png')
 $bmp.Save($dest,[Drawing.Imaging.ImageFormat]::Png);$g.Dispose();$bmp.Dispose()
}
$font.Dispose();$titleFont.Dispose()
Write-Output 'Rendered centroid and four case previews.'
