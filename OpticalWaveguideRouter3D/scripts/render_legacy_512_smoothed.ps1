param([string]$InputJson,[string]$OutputPng)
Add-Type -AssemblyName System.Drawing
$data=Get-Content -LiteralPath $InputJson -Raw | ConvertFrom-Json
$bitmap=New-Object System.Drawing.Bitmap 1100,1000
$g=[System.Drawing.Graphics]::FromImage($bitmap)
$g.SmoothingMode=[System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::White)
$font=New-Object System.Drawing.Font 'Arial',14
$brush=[System.Drawing.Brushes]::Black
$scale=[Math]::Min(940.0/($data.xmax-$data.xmin),800.0/150.0)
$left=90.0
$bottom=890.0
$ordinary=New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(85,35,95,180)),0.8
$special=New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(170,225,95,20)),1.2
$axis=New-Object System.Drawing.Pen ([System.Drawing.Color]::Gray),1
try {
 foreach($route in $data.routes) {
  $pen=$ordinary
  if($route.special){$pen=$special}
  foreach($s in $route.segments) {
   if($s.kind -eq 'line'){
    $g.DrawLine($pen,[single]($left+($s.x1-$data.xmin)*$scale),[single]($bottom-$s.y1*$scale),[single]($left+($s.x2-$data.xmin)*$scale),[single]($bottom-$s.y2*$scale))
   } else {
    $g.DrawArc($pen,[single]($left+($s.cx-$s.r-$data.xmin)*$scale),[single]($bottom-($s.cy+$s.r)*$scale),[single](2*$s.r*$scale),[single](2*$s.r*$scale),[single](-$s.start_deg),[single](-$s.sweep_deg))
   }
  }
 }
 $g.DrawRectangle($axis,[single]$left,[single]($bottom-150*$scale),[single](($data.xmax-$data.xmin)*$scale),[single](150*$scale))
 foreach($y in @(0,25,50,75,100,125,150)){
  $g.DrawString([string]$y,$font,$brush,[single]30,[single]($bottom-$y*$scale-10))
 }
 for($x=[Math]::Ceiling($data.xmin/50)*50;$x -le $data.xmax;$x+=50){
  $g.DrawString([string]$x,$font,$brush,[single]($left+($x-$data.xmin)*$scale-10),[single]910)
 }
 $g.DrawString('Legacy 512 analytic centerlines | equal x/y scale | mm',$font,$brush,90,20)
 $g.DrawString('Blue: 454 ordinary | Orange: 58 independent special-Z (allocator unsupported)',$font,$brush,90,50)
 $g.DrawString('Zero-width geometry; crossings present; not a collision-free result',$font,$brush,90,945)
 $g.DrawString('x (mm)',$font,$brush,950,910)
 $g.DrawString('y (mm)',$font,$brush,10,105)
 $bitmap.Save($OutputPng,[System.Drawing.Imaging.ImageFormat]::Png)
} finally {$g.Dispose();$bitmap.Dispose();$font.Dispose();$ordinary.Dispose();$special.Dispose();$axis.Dispose()}
