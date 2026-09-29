<#
  GKG deploy watcher (Windows), the same as Eat Train Feel's.

  Waits for request files in this repo and does exactly one thing for each.
  The content of a request is never run; at most it picks between fixed builds.

    .push-request          git push origin master (never forced)
                           -> .push.log, .push-status.json
    .deploy-request        docker compose up -d --build on the committed tree
                           -> .deploy.log, .deploy-status.json, a line in .deploy-history.log
    .garmin-build-request  the watch app in garmin/ with the Connect IQ SDK set in the
                           SDK Manager and the developer key in C:\garmin-keys
                           -> .garmin-build.log, .garmin-build-status.json

  What the Garmin request may say (anything else, or nothing, is "build"):

      echo build         > .garmin-build-request   ->  garmin\bin\GKG.prg (fenix 8 47/51 mm)
      echo build fr165   > .garmin-build-request   ->  garmin\bin\GKG-fr165.prg
      echo export        > .garmin-build-request   ->  garmin\bin\GKG.iq (store package)

  The word "beta" anywhere builds the beta app instead of the public one:
  manifest-beta.xml through monkey-beta.jungle, into a file with -beta in its
  name. The two differ only in the app id (a beta app cannot be published).

      echo export beta   > .garmin-build-request   ->  garmin\bin\GKG-beta.iq

  The key is only read here; it never leaves this machine and is never in the repo.

  Installed once as a logon task by scripts/install-deploy-watcher.ps1. A
  change to this file takes effect when the task starts again (sign out and
  in, or End and Run the task in Task Scheduler).
#>

$ErrorActionPreference = "Continue"
$Repo     = Split-Path -Parent $PSScriptRoot
$Request  = Join-Path $Repo ".deploy-request"
$Log      = Join-Path $Repo ".deploy.log"
$History  = Join-Path $Repo ".deploy-history.log"
$Status   = Join-Path $Repo ".deploy-status.json"
$Health   = "http://localhost:8791/api/health"
$PushRequest = Join-Path $Repo ".push-request"
$PushLog     = Join-Path $Repo ".push.log"
$PushStatus  = Join-Path $Repo ".push-status.json"
$GarminRequest = Join-Path $Repo ".garmin-build-request"
$GarminLog     = Join-Path $Repo ".garmin-build.log"
$GarminStatus  = Join-Path $Repo ".garmin-build-status.json"
$GarminKeys    = "C:\garmin-keys"
$GarminDevice  = "fenix847mm"
$GarminName    = "GKG"

function Write-Log([string]$text) {
  Add-Content -Path $Log -Value $text -Encoding utf8
}

function Run([string]$command) {
  Write-Log ""
  Write-Log "> $command"
  # Through cmd so docker's progress on stderr is captured as text, not as PowerShell errors.
  $out = & cmd.exe /c "$command 2>&1"
  $code = $LASTEXITCODE
  if ($out) { Write-Log (($out | Out-String).TrimEnd()) }
  return $code
}

Set-Location $Repo

while ($true) {
  if (Test-Path $PushRequest) {
    Remove-Item $PushRequest -Force -ErrorAction SilentlyContinue
    $pStarted = Get-Date
    Set-Content -Path $PushStatus -Value (@{ state = "running"; startedAt = $pStarted.ToString("o") } | ConvertTo-Json -Compress) -Encoding utf8
    $pOut = & cmd.exe /c "git -C `"$Repo`" push origin master 2>&1"
    $pCode = $LASTEXITCODE
    $pCommit = (& git -C $Repo log --oneline -1 2>$null) -join ""
    Set-Content -Path $PushLog -Value ("Push $($pStarted.ToString('yyyy-MM-dd HH:mm:ss'))  $pCommit`r`n" + (($pOut | Out-String).TrimEnd())) -Encoding utf8
    Set-Content -Path $PushStatus -Value (@{ state = $(if ($pCode -eq 0) { "ok" } else { "failed" }); startedAt = $pStarted.ToString("o"); exitCode = $pCode; commit = $pCommit } | ConvertTo-Json -Compress) -Encoding utf8
  }

  if (Test-Path $GarminRequest) {
    $gWhat = ""
    try { $gWhat = ((Get-Content $GarminRequest -Raw -ErrorAction SilentlyContinue) + "").Trim().ToLower() } catch { $gWhat = "" }
    $gBeta = ($gWhat -match '(^|\s)beta(\s|$)')
    if ($gBeta) { $gWhat = ($gWhat -replace '(^|\s)beta(\s|$)', ' ').Trim() }
    $gTag = $(if ($gBeta) { "-beta" } else { "" })
    $gExport = ($gWhat -eq "export")
    $gDevice = $GarminDevice
    if ($gWhat -match '^build\s+([A-Za-z0-9]{2,32})$') { $gDevice = $Matches[1] }
    Remove-Item $GarminRequest -Force -ErrorAction SilentlyContinue
    $gStarted = Get-Date
    Set-Content -Path $GarminStatus -Value (@{ state = "running"; startedAt = $gStarted.ToString("o") } | ConvertTo-Json -Compress) -Encoding utf8
    $gLines = @("Garmin $(if ($gExport) { 'export' } else { 'build' }) $($gStarted.ToString('yyyy-MM-dd HH:mm:ss'))  $((& git -C $Repo log --oneline -1 2>$null) -join '')")
    $gCode = 1
    $cfg = Join-Path $env:APPDATA "Garmin\ConnectIQ\current-sdk.cfg"
    $key = Get-ChildItem -Path $GarminKeys -Filter *.der -ErrorAction SilentlyContinue | Select-Object -First 1
    $jungle = Join-Path $Repo $(if ($gBeta) { "garmin\monkey-beta.jungle" } else { "garmin\monkey.jungle" })
    if (-not (Test-Path $jungle)) {
      $gLines += "No watch app yet: $jungle is missing."
    } elseif (-not (Test-Path $cfg)) {
      $gLines += "No Connect IQ SDK: $cfg is missing. Pick one in the SDK Manager."
    } elseif (-not $key) {
      $gLines += "No developer key: no .der file in $GarminKeys."
    } else {
      $bin = (Get-Content $cfg -Raw).Trim()
      $monkeyc = Join-Path $bin "bin\monkeyc.bat"
      if (-not (Test-Path $monkeyc)) { $monkeyc = Join-Path $bin "monkeyc.bat" }
      New-Item -ItemType Directory -Force -Path (Join-Path $Repo "garmin\bin") | Out-Null
      if ($gExport) {
        $out = Join-Path $Repo "garmin\bin\$GarminName$gTag.iq"
        $gOut = & cmd.exe /c "`"$monkeyc`" -e -r -f `"$jungle`" -y `"$($key.FullName)`" -o `"$out`" -w 2>&1"
      } else {
        $name = $(if ($gDevice -eq $GarminDevice) { "$GarminName$gTag.prg" } else { "$GarminName$gTag-$gDevice.prg" })
        $out = Join-Path $Repo "garmin\bin\$name"
        $gOut = & cmd.exe /c "`"$monkeyc`" -f `"$jungle`" -d $gDevice -y `"$($key.FullName)`" -o `"$out`" -w 2>&1"
      }
      $gCode = $LASTEXITCODE
      $gLines += ($gOut | Out-String).TrimEnd()
      if ($gCode -eq 0 -and (Test-Path $out)) { $gLines += "Built: $out ($((Get-Item $out).Length) bytes)" }
    }
    Set-Content -Path $GarminLog -Value ($gLines -join "`r`n") -Encoding utf8
    Set-Content -Path $GarminStatus -Value (@{ state = $(if ($gCode -eq 0) { "ok" } else { "failed" }); startedAt = $gStarted.ToString("o"); exitCode = $gCode } | ConvertTo-Json -Compress) -Encoding utf8
  }

  if (Test-Path $Request) {
    Remove-Item $Request -Force -ErrorAction SilentlyContinue
    $started = Get-Date
    Set-Content -Path $Log -Value "Deploy started $($started.ToString('yyyy-MM-dd HH:mm:ss'))" -Encoding utf8
    Set-Content -Path $Status -Value (@{ state = "running"; startedAt = $started.ToString("o") } | ConvertTo-Json -Compress) -Encoding utf8

    $commit = (& git -C $Repo log --oneline -1 2>$null) -join ""
    Write-Log "Commit: $commit"

    $code = Run "docker compose up -d --build"

    $healthy = $false
    if ($code -eq 0) {
      for ($i = 0; $i -lt 30 -and -not $healthy; $i++) {
        Start-Sleep -Seconds 2
        try {
          $r = Invoke-WebRequest -Uri $Health -UseBasicParsing -TimeoutSec 5
          if ($r.StatusCode -eq 200) { $healthy = $true }
        } catch { }
      }
      Run "docker compose ps" | Out-Null
      Run "docker compose logs --tail 40 gkg" | Out-Null
    }

    $ok = ($code -eq 0) -and $healthy
    $took = [int]((Get-Date) - $started).TotalSeconds
    $verdict = if ($ok) { "DEPLOY OK" } elseif ($code -ne 0) { "DEPLOY FAILED (docker exit $code)" } else { "DEPLOY FAILED (app did not answer on $Health)" }
    Write-Log ""
    Write-Log "$verdict in ${took}s"
    Add-Content -Path $History -Value "$($started.ToString('yyyy-MM-dd HH:mm:ss'))  $verdict  $commit" -Encoding utf8
    Set-Content -Path $Status -Value (@{ state = $(if ($ok) { "ok" } else { "failed" }); startedAt = $started.ToString("o"); seconds = $took; exitCode = $code; healthy = $healthy; commit = $commit } | ConvertTo-Json -Compress) -Encoding utf8
  }
  Start-Sleep -Seconds 3
}
