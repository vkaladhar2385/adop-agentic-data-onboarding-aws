#!/usr/bin/env pwsh
# Push the current (or given) branch to every configured remote (or a given subset),
# continuing past failures and printing a per-remote summary. Exit 1 if any failed.
param(
    [string]$Branch,
    [string[]]$Remotes = @()
)

$ErrorActionPreference = "Continue"

if (-not $Branch) {
    $Branch = (git rev-parse --abbrev-ref HEAD).Trim()
}
if (-not $Remotes -or $Remotes.Count -eq 0) {
    $Remotes = @(git remote)
}

if (-not $Remotes -or $Remotes.Count -eq 0) {
    Write-Error "No git remotes configured."
    exit 2
}

Write-Host "Branch: $Branch"
Write-Host "Remotes: $($Remotes -join ', ')"
Write-Host ""

$results = @()
foreach ($r in $Remotes) {
    Write-Host "==> git push -u $r $Branch"
    git push -u $r $Branch
    $results += [pscustomobject]@{ Remote = $r; ExitCode = $LASTEXITCODE }
    Write-Host ""
}

Write-Host "=== Push summary ==="
foreach ($res in $results) {
    $status = if ($res.ExitCode -eq 0) { "OK" } else { "FAILED (exit $($res.ExitCode))" }
    Write-Host ("{0,-14} {1}" -f $res.Remote, $status)
}

$failed = @($results | Where-Object { $_.ExitCode -ne 0 })
if ($failed.Count -gt 0) { exit 1 } else { exit 0 }
