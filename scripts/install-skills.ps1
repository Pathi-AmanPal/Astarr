<#
.SYNOPSIS
  Set up the vendored skills on Windows.

.DESCRIPTION
  Repairs .agent\skills\impeccable, which Impeccable's scripts resolve against.
  Git for Windows checks symlinks out as plain text files unless core.symlinks
  is enabled, so this recreates it as a directory junction (no admin needed).

  With -Global, also installs every skill into %USERPROFILE%\.claude so they
  load in all projects.

.EXAMPLE
  .\scripts\install-skills.ps1
  .\scripts\install-skills.ps1 -Global
  .\scripts\install-skills.ps1 -Global -Force
#>
[CmdletBinding()]
param(
  [switch]$Global,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$claudeHome = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' }

$source = Join-Path $root '.claude\skills\impeccable'
if (-not (Test-Path (Join-Path $source 'scripts\context.mjs'))) {
  throw ".claude\skills\impeccable is missing. Run scripts/update-skills.sh first."
}

# ---------------------------------------------------------------- repo repair
$agentSkills = Join-Path $root '.agent\skills'
$link = Join-Path $agentSkills 'impeccable'
New-Item -ItemType Directory -Force -Path $agentSkills | Out-Null

$item = Get-Item $link -Force -ErrorAction SilentlyContinue
$isLink = $item -and $item.LinkType -in @('SymbolicLink', 'Junction')

if ($isLink -and (Test-Path (Join-Path $link 'scripts\context.mjs'))) {
  Write-Host "ok   .agent\skills\impeccable is a $($item.LinkType)"
} else {
  if ($item) { Remove-Item $link -Recurse -Force }
  # Junctions work without Developer Mode or admin; symlinks generally do not.
  cmd /c mklink /J "$link" "$source" | Out-Null
  if (Test-Path (Join-Path $link 'scripts\context.mjs')) {
    Write-Host 'fix  .agent\skills\impeccable recreated as a junction'
  } else {
    Copy-Item $source $link -Recurse -Force
    Write-Host 'warn .agent\skills\impeccable copied (junction failed)'
  }
}

Write-Host ''
Write-Host 'Tip: run `git config core.symlinks true` in this repo so future clones'
Write-Host '     keep the link, then re-run this script.'

# ------------------------------------------------------------- global install
if (-not $Global) { return }

Write-Host ''
Write-Host "Installing into $claudeHome"
$skillsDest = Join-Path $claudeHome 'skills'
$agentsDest = Join-Path $claudeHome 'agents'
New-Item -ItemType Directory -Force -Path $skillsDest, $agentsDest | Out-Null

foreach ($src in Get-ChildItem (Join-Path $root '.claude\skills') -Directory) {
  $dest = Join-Path $skillsDest $src.Name
  if ((Test-Path $dest) -and -not $Force) {
    Write-Host "skip $($src.Name) (already installed; -Force to overwrite)"
    continue
  }
  if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
  Copy-Item $src.FullName $dest -Recurse -Force
  Write-Host "  +  $($src.Name)"
}

Copy-Item (Join-Path $root '.claude\agents\impeccable-*.md') $agentsDest -Force
Write-Host '  +  4 impeccable agents'

# Pre-approve the script calls at their global path so they don't prompt.
$settingsPath = Join-Path $claudeHome 'settings.json'
$globalScripts = (Join-Path $skillsDest 'impeccable\scripts') -replace '\\', '/'
$want = @(
  "Bash(node $globalScripts/*)",
  'Bash(node .claude/skills/impeccable/scripts/*)',
  'Bash(node .agent/skills/impeccable/scripts/*)',
  'Bash(npx impeccable *)'
)

$settings = $null
if (Test-Path $settingsPath) {
  try {
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
  } catch {
    Write-Host "warn $settingsPath is not valid JSON - add these to permissions.allow yourself:"
    $want | ForEach-Object { Write-Host "       $_" }
  }
}

if ($null -eq $settings) { $settings = [pscustomobject]@{} }
if (-not $settings.PSObject.Properties['permissions']) {
  $settings | Add-Member permissions ([pscustomobject]@{}) -Force
}
if (-not $settings.permissions.PSObject.Properties['allow']) {
  $settings.permissions | Add-Member allow @() -Force
}

$allow = [System.Collections.ArrayList]@($settings.permissions.allow)
$added = 0
foreach ($w in $want) {
  if ($allow -notcontains $w) { [void]$allow.Add($w); $added++ }
}
if ($added -gt 0) {
  $settings.permissions.allow = $allow.ToArray()
  $settings | ConvertTo-Json -Depth 20 | Set-Content $settingsPath -Encoding UTF8
  Write-Host "  +  $added permission(s) in $settingsPath"
} else {
  Write-Host '  =  permissions already present'
}

Write-Host ''
Write-Host 'Done. Restart Claude Code, then type / to see the skills in any project.'
