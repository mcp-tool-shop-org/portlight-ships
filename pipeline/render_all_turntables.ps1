# Render an 8-view Blender turntable for every GLB in the mesh store for a hull.
#
# This is the verification gate for stage 2: identity must hold across all eight
# headings. Diffusion-per-heading never could; a textured mesh on a deterministic
# turntable is the whole reason the mesh stage exists.
#
# Usage:
#   pwsh pipeline/render_all_turntables.ps1 -Hull galleon
param(
    [string]$Hull = "galleon",
    [string]$Store = "E:\AI-Models\mesh-store\portlight-ships",
    [string]$OutRoot = "E:\AI\portlight-ships\hulls",
    [int]$Views = 8,
    [int]$Size = 768
)

$blender = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
$script  = "E:\AI\portlight-ships\pipeline\turntable.py"
$src     = Join-Path $Store $Hull
$dst     = Join-Path $OutRoot "$Hull\turntable"

if (-not (Test-Path $blender)) { throw "Blender not found at $blender" }
New-Item -ItemType Directory -Force $dst | Out-Null

$glbs = Get-ChildItem $src -Filter *.glb | Sort-Object Name
Write-Output "rendering $($glbs.Count) meshes x $Views views"

foreach ($g in $glbs) {
    $subject = $g.BaseName
    $out = Join-Path $dst $subject
    if (Test-Path (Join-Path $out "$subject`_$($Views-1).png")) {
        Write-Output "SKIP  $subject (already rendered)"
        continue
    }
    New-Item -ItemType Directory -Force $out | Out-Null
    Write-Output "RENDER $subject"
    & $blender -b --python $script -- --glb $g.FullName --out $out --views $Views --size $Size --tag $subject 2>&1 |
        Select-String "bbox|ERROR" | ForEach-Object { "   $_" }
}
Write-Output "TURNTABLES DONE"
