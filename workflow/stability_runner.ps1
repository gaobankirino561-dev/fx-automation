param(
    [int]$NMin = 5,
    [int]$TradesMin = 30,
    [string]$WideningLevels = "[(1.05,0,20),(1.02,-0.05,22),(1.00,-0.10,25)]",
    [string]$Stages = "20,30,40,60",
    [string]$Out = "results",
    [string]$BaseGrid = "config/param_grid_base.yaml",
    [string]$AugGrid = "config/param_grid_aug.yaml",
    [int]$MaxCombinations = 2000,
    [string]$LogFile = "",
    [switch]$Pack,
    [string]$EquityStart,
    [string]$EquityEnd,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path $scriptRoot
Push-Location $repoRoot

if (-not (Test-Path $Out)) {
    New-Item -ItemType Directory -Path $Out | Out-Null
}
$outResolved = (Resolve-Path $Out).ProviderPath

if ([Console]::OutputEncoding.WebName -ne 'utf-8') {
    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    } catch {
        Write-Host "Warning: failed to switch console output encoding to UTF-8." -ForegroundColor Yellow
    }
}

function Write-RunMeta {
    param(
        [string]$Path,
        [hashtable]$Meta
    )
    if ($Meta.Contains("files")) {
        $unique = @()
        foreach ($f in $Meta.files) {
            if ($f -and ($unique -notcontains $f)) { $unique += $f }
        }
        $Meta.files = $unique
        $Meta.files_count = $unique.Count
    }
    $json = $Meta | ConvertTo-Json -Depth 10
    Set-Content -Path $Path -Value $json -Encoding UTF8
    Write-Host ("Run meta saved to: {0}" -f $Path) -ForegroundColor DarkGray
}

function Invoke-PythonCommand {
    param(
        [string]$Python,
        [string[]]$Arguments,
        [string]$LogFile,
        [switch]$CaptureOutput,
        [switch]$SuppressHostOutput
    )

    $output = $null
    $exitCode = 0

    if ($LogFile) {
        $logDir = Split-Path $LogFile
        if ($logDir) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
        & $Python @Arguments *> $LogFile
        $exitCode = $LASTEXITCODE
        if ($CaptureOutput) {
            if (Test-Path $LogFile) {
                $output = Get-Content -Path $LogFile -Raw
            } else {
                $output = ""
            }
        }
    } else {
        if ($CaptureOutput -or $SuppressHostOutput) {
            $output = & $Python @Arguments
            $exitCode = $LASTEXITCODE
            if (-not $SuppressHostOutput -and $output) {
                $output | ForEach-Object { Write-Host $_ }
            }
        } else {
            & $Python @Arguments
            $exitCode = $LASTEXITCODE
        }
    }

    $captured = ""
    if ($CaptureOutput) {
        if ($output -is [System.Array]) {
            $captured = ($output -join "`n")
        } elseif ($null -ne $output) {
            $captured = [string]$output
        }
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = $captured
    }
}

function Invoke-Generator {
    param(
        [string]$Mode,
        [string[]]$Splits,
        [string]$Timestamp,
        [string]$Grid,
        [string]$ResultsDir,
        [switch]$DryRun,
        [string]$AugGrid,
        [string]$Stage,
        [int]$MaxCombinations,
        [string]$Python,
        [string]$LogFile
    )
    $cmd = @('workflow/wf_stability_generate.py',
        '--mode', $Mode,
        '--grid', $Grid,
        '--splits') + $Splits + @(
        '--ts', $Timestamp,
        '--results-dir', $ResultsDir
    )
    if ($Mode -eq 'augment') {
        $cmd += @('--aug', $AugGrid, '--stage', $Stage, '--max-combinations', $MaxCombinations)
    }
    if ($DryRun) { $cmd += '--dry-run' }

    $invokeResult = Invoke-PythonCommand -Python $Python -Arguments $cmd -LogFile $LogFile -CaptureOutput -SuppressHostOutput
    if ($invokeResult.ExitCode -ne 0) {
        Write-Host "Generator exited with code $($invokeResult.ExitCode)" -ForegroundColor Red
        throw "Generator failed"
    }
    $info = $invokeResult.Output | ConvertFrom-Json
    if ($info.error) {
        throw $info.error
    }
    $combosTotal = if ($null -ne $info.combos_total) { [int]$info.combos_total } else { 0 }
    $duplicatesSkipped = if ($null -ne $info.duplicates_skipped) { [int]$info.duplicates_skipped } else { 0 }
    $combosAfterFilter = if ($null -ne $info.combos_after_filter) { [int]$info.combos_after_filter } else { 0 }
    $combosScheduled = if ($null -ne $info.combos_scheduled) { [int]$info.combos_scheduled } else { 0 }
    $combosEvaluated = if ($null -ne $info.combos_evaluated) { [int]$info.combos_evaluated } else { 0 }
    $durationSec = if ($null -ne $info.duration_sec) { [double]$info.duration_sec } else { 0.0 }
    $isDry = if ($null -ne $info.dry_run) { [bool]$info.dry_run } else { $false }

    $result = [ordered]@{
        mode               = $info.mode
        stage              = $info.stage
        combos_total       = $combosTotal
        duplicates_skipped = $duplicatesSkipped
        combos_after_filter = $combosAfterFilter
        combos_scheduled   = $combosScheduled
        combos_evaluated   = $combosEvaluated
        raw_csv            = $info.raw_csv
        summary_csv        = $info.summary_csv
        duration_sec       = $durationSec
        dry_run            = $isDry
    }
    return $result
}

function Invoke-Selection {
    param(
        [string]$SummaryPath,
        [string]$TimestampTag,
        [string]$Python,
        [switch]$DryRun,
        [int]$NMin,
        [int]$TradesMin,
        [string]$WideningLevels,
        [string]$Stages,
        [string]$OutDir,
        [string]$LogFile
    )
    $cmd = @('analysis/select_candidates.py',
        '--summary', $SummaryPath,
        '--n-min', $NMin,
        '--trades-min', $TradesMin,
        '--widening-levels', $WideningLevels,
        '--stages', $Stages,
        '--out', $OutDir,
        '--ts', $TimestampTag
    )
    if ($DryRun) { $cmd += '--dry-run' }
    $selectionResult = Invoke-PythonCommand -Python $Python -Arguments $cmd -LogFile $LogFile -SuppressHostOutput
    if ($selectionResult.ExitCode -ne 0) {
        throw "select_candidates failed"
    }
    $metaPath = Join-Path $OutDir ("select_candidates_{0}.json" -f $TimestampTag)
    if (-not (Test-Path $metaPath)) {
        throw "selection meta JSON not found: $metaPath"
    }
    $meta = Get-Content -Path $metaPath -Raw | ConvertFrom-Json
    $logPath = [System.IO.Path]::ChangeExtension($metaPath, '.log')
    return ,@{
        MetaPath = $metaPath
        LogPath  = $(if (Test-Path $logPath) { $logPath } else { $null })
        Data     = $meta
    }
}

function Summarise-Selection {
    param(
        [hashtable]$Result,
        [ref]$RunMetaSelection,
        [int]$NMin
    )
    $selectionMeta = $RunMetaSelection.Value
    $metaData = $Result.Data
    $selectionMeta.meta_json = $Result.MetaPath
    $selectionMeta.log = $Result.LogPath
    $selectionMeta.summary_csv = $metaData.summary_csv
    $selectionMeta.raw_csv = $metaData.raw_csv
    $selectionMeta.levels = $metaData.levels
    $selectionMeta.duplicates_removed = $metaData.duplicates_removed
    $selectionMeta.stages = $metaData.stages

    $candidateCount = ($metaData.selected | Measure-Object).Count
    $selectionMeta.candidate_count = $candidateCount

    $reasonTotals = [ordered]@{ pf = 0; ret = 0; dd = 0; trades = 0 }
    $cumulative = 0
    foreach ($level in ($metaData.levels | ForEach-Object { $_ })) {
        $accepted = [int]$level.accepted
        $excluded = $level.excluded
        $reasonTotals.pf += [int]$excluded.pf
        $reasonTotals.ret += [int]$excluded.ret
        $reasonTotals.dd += [int]$excluded.dd
        $reasonTotals.trades += [int]$excluded.trades
        $cumulative += $accepted
        if (-not $selectionMeta.Contains('adoption_level') -and $cumulative -ge $NMin) {
            $selectionMeta.adoption_level = $level.name
        }
    }
    $selectionMeta.reason_totals = $reasonTotals

    if ($candidateCount -ge $NMin) {
        $adoptionLevel = if ($selectionMeta.adoption_level) { $selectionMeta.adoption_level } else { ($metaData.levels[-1]).name }
        $selectionMeta.adoption_level = $adoptionLevel
        Write-Host ("Minimum quota reached: level={0} selected={1}" -f $adoptionLevel, $candidateCount) -ForegroundColor Green
        $selectionMeta.blocking_condition = $null
    } else {
        Write-Host ("Minimum quota not reached (found {0}, need {1})." -f $candidateCount, $NMin) -ForegroundColor Yellow
        $limiter = $reasonTotals.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1
        if ($limiter -and $limiter.Value -gt 0) {
            $reasonMap = @{
                pf     = 'PF threshold (AvgPF)'
                ret    = 'Return threshold (AvgRet)'
                dd     = 'Drawdown threshold (MaxDD)'
                trades = 'Trades minimum'
            }
            $selectionMeta.blocking_condition = [ordered]@{
                key         = $limiter.Key
                description = $reasonMap[$limiter.Key]
                failures    = $limiter.Value
            }
            Write-Host ("Most blocking condition: {0} (failures={1})" -f $reasonMap[$limiter.Key], $limiter.Value) -ForegroundColor Yellow
        } else {
            Write-Host "No explicit failures recorded; check source summary/trades data." -ForegroundColor Yellow
            $selectionMeta.blocking_condition = [ordered]@{
                key         = 'unknown'
                description = 'No combinations evaluated'
                failures    = 0
            }
        }
    }

    $RunMetaSelection.Value = $selectionMeta
    return $candidateCount
}

# Git SHA for reproducibility
$gitSha = $null
try {
    $gitSha = (& git rev-parse --short HEAD).Trim()
} catch {
    Write-Host "Warning: failed to read git short SHA." -ForegroundColor Yellow
}

$gitStatusLines = @()
$gitStatusSample = @()
$gitDirty = $false
try {
    $gitStatusLines = (& git status --porcelain)
    if ($null -eq $gitStatusLines) { $gitStatusLines = @() }
    elseif (-not ($gitStatusLines -is [System.Array])) { $gitStatusLines = @($gitStatusLines) }
    $gitStatusLines = $gitStatusLines | Where-Object { $_ -and $_.Trim() }
    if ($gitStatusLines.Count -gt 0) {
        $gitDirty = $true
        $gitStatusSample = $gitStatusLines | Select-Object -First 10
    }
} catch {
    Write-Host "Warning: failed to read git status." -ForegroundColor Yellow
    $gitStatusLines = @()
    $gitStatusSample = @()
}
if ($gitStatusSample.Count -eq 0) { $gitStatusSample = @() }

$runTimestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$runMetaPath = Join-Path $outResolved ("run_meta_{0}.json" -f $runTimestamp)

$splitValues = $Stages.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
$splitInts = $splitValues | ForEach-Object { [int]$_ }
$stabilitySplits = $splitInts | Where-Object { $_ -lt 40 }
if (-not $stabilitySplits) {
    throw "Stages must include at least one split below 40 for the 20/30 phase."
}
$validationSplits = $splitInts | Where-Object { $_ -ge 40 }
if (-not $validationSplits) {
    $validationSplits = @(40, 60)
}

$runMeta = [ordered]@{
    timestamp = $runTimestamp
    dry_run   = [bool]$DryRun
    git_sha   = $gitSha
    git_status = [ordered]@{
        dirty   = [bool]$gitDirty
        changed = $gitStatusLines.Count
        sample  = $gitStatusSample
    }
    args      = [ordered]@{
        n_min            = $NMin
        trades_min       = $TradesMin
        widening_levels  = $WideningLevels
        stages           = $Stages
        stability_splits = $stabilitySplits
        validation_splits = $validationSplits
        out_dir          = $outResolved
        base_grid        = $BaseGrid
        aug_grid         = $AugGrid
        max_combinations = $MaxCombinations
        pack             = [bool]$Pack
    }
    files = @()
    generation = @()
}
if ($EquityStart) { $runMeta.args.equity_start = $EquityStart }
if ($EquityEnd) { $runMeta.args.equity_end = $EquityEnd }

$exitCode = 0

try {
    $python = 'python'

    Write-Host "`n== Stability Grid Generation ==" -ForegroundColor Cyan
    $stabilitySplitStrings = $stabilitySplits | ForEach-Object { $_.ToString() }
    $genBase = Invoke-Generator -Mode 'base' -Splits $stabilitySplitStrings -Timestamp $runTimestamp -Grid $BaseGrid -ResultsDir $outResolved -DryRun:$DryRun -Python $python -LogFile $LogFile
    $runMeta.generation += $genBase
    $runMeta.files += $genBase.raw_csv
    $runMeta.files += $genBase.summary_csv
    Write-Host ("Base grid combos: total={0}, after_filter={1}, scheduled={2}, evaluated={3}, skipped={4}, duration={5:n2}s" -f `
        $genBase.combos_total, $genBase.combos_after_filter, $genBase.combos_scheduled, $genBase.combos_evaluated, $genBase.duplicates_skipped, $genBase.duration_sec) -ForegroundColor DarkGray
    Write-RunMeta -Path $runMetaPath -Meta $runMeta
    $summaryPath = $genBase.summary_csv

    $augStages = @()
    if (Test-Path $AugGrid) {
        $augConfig = Get-Content -Path $AugGrid -Raw | ConvertFrom-Json
        $augStages = $augConfig.stages
    }

    Write-Host "`n== Stability Selection (20/30) ==" -ForegroundColor Cyan
    $selectionIteration = 1
    $selectionTag = "{0}_sel{1}" -f $runTimestamp, $selectionIteration
    $selectionResult = Invoke-Selection -SummaryPath $summaryPath -TimestampTag $selectionTag -Python $python -DryRun:$DryRun -NMin $NMin -TradesMin $TradesMin -WideningLevels $WideningLevels -Stages $Stages -OutDir $outResolved -LogFile $LogFile

    $runMeta.selection = [ordered]@{
        augmentations = @()
    }
    $runMeta.files += $selectionResult.MetaPath
    if ($selectionResult.LogPath) { $runMeta.files += $selectionResult.LogPath }
    if ($selectionResult.Data.raw_csv) { $runMeta.files += $selectionResult.Data.raw_csv }
    if ($selectionResult.Data.summary_csv) { $runMeta.files += $selectionResult.Data.summary_csv }

    $candidateCount = Summarise-Selection -Result $selectionResult -RunMetaSelection ([ref]$runMeta.selection) -NMin $NMin
    Write-RunMeta -Path $runMetaPath -Meta $runMeta

    $stageIndex = 0
    foreach ($stage in $augStages) {
        if ($candidateCount -ge $NMin) { break }
        $stageIndex += 1
        Write-Host ("Applying augmentation stage {0} ({1})" -f $stageIndex, $stage.name) -ForegroundColor Cyan
        $stageInfo = Invoke-Generator -Mode 'augment' -Splits $stabilitySplitStrings -Timestamp $runTimestamp -Grid $BaseGrid -ResultsDir $outResolved -DryRun:$DryRun -AugGrid $AugGrid -Stage $stage.name -MaxCombinations $MaxCombinations -Python $python -LogFile $LogFile
        $runMeta.generation += $stageInfo
        $runMeta.selection.augmentations += $stageInfo
        $runMeta.files += $stageInfo.raw_csv
        $runMeta.files += $stageInfo.summary_csv
        Write-Host ("Stage {0} combos: total={1}, after_filter={2}, scheduled={3}, evaluated={4}, skipped={5}, duration={6:n2}s" -f `
            $stage.name, $stageInfo.combos_total, $stageInfo.combos_after_filter, $stageInfo.combos_scheduled, $stageInfo.combos_evaluated, $stageInfo.duplicates_skipped, $stageInfo.duration_sec) -ForegroundColor DarkGray

        $selectionIteration += 1
        $selectionTag = "{0}_sel{1}" -f $runTimestamp, $selectionIteration
        $selectionResult = Invoke-Selection -SummaryPath $summaryPath -TimestampTag $selectionTag -Python $python -DryRun:$DryRun -NMin $NMin -TradesMin $TradesMin -WideningLevels $WideningLevels -Stages $Stages -OutDir $outResolved -LogFile $LogFile
        $runMeta.files += $selectionResult.MetaPath
        if ($selectionResult.LogPath) { $runMeta.files += $selectionResult.LogPath }
        $candidateCount = Summarise-Selection -Result $selectionResult -RunMetaSelection ([ref]$runMeta.selection) -NMin $NMin
        Write-RunMeta -Path $runMetaPath -Meta $runMeta
    }

    Write-Host "`nFinal strict criteria: AvgPF>=1.05, AvgRet>=0, MaxDD<=20, PF_drift>=-0.10, trades>=30" -ForegroundColor DarkCyan
    Write-Host "Final criteria: AvgPF>=1.05, AvgRet>=0, MaxDD<=20, PF_drift>=-0.10, trades>=30" -ForegroundColor DarkCyan

    $commitGate = [ordered]@{
        requested = [bool]$Pack
    }
    $skipFurther = $false
    $finalCsv = $null
    $packParsed = $null

    if ($candidateCount -lt $NMin) {
        Write-Host "No candidates met the thresholds. Consider widening criteria and rerun." -ForegroundColor Yellow
        Write-Host "Skipping 40/60 validation." -ForegroundColor Yellow
        $runMeta.validation = [ordered]@{
            skipped = $true
            blocking_condition = $runMeta.selection.blocking_condition
        }
        if ($Pack) {
            $commitGate.status = 'skipped'
            $commitGate.reason = 'No candidates met thresholds; pack generation skipped.'
            $commitGate.passed = $false
            $exitCode = 1
        } else {
            $commitGate.status = 'not_requested'
            $commitGate.reason = 'Pack not requested'
            $commitGate.passed = $null
        }
        $skipFurther = $true
    }

    if (-not $skipFurther) {
        Write-Host "`n== 40/60 Validation ==" -ForegroundColor Cyan
        $validationSplitStrings = $validationSplits | ForEach-Object { $_.ToString() }
        $wfArgs = @('workflow/wf_stability.py', '--meta', $selectionResult.MetaPath, '--splits') + $validationSplitStrings + @(
            '--strict-pf-min', '1.05',
            '--strict-ret-min', '0',
            '--strict-dd-max', '20',
            '--strict-pf-drift', '-0.10'
        )
        if ($DryRun) { $wfArgs += '--dry-run' }
        $wfInvoke = Invoke-PythonCommand -Python $python -Arguments $wfArgs -LogFile $LogFile
        if ($wfInvoke.ExitCode -ne 0) {
        throw "wf_stability.py failed with exit code $($wfInvoke.ExitCode)"
    }

        $runMeta.validation = [ordered]@{
            dry_run = [bool]$DryRun
            splits  = $validationSplitStrings
            strict  = [ordered]@{
                pf_min       = 1.05
                ret_min      = 0
                dd_max       = 20
                pf_drift_min = -0.10
            }
        }
        Write-RunMeta -Path $runMetaPath -Meta $runMeta

        $extMetaPattern = Join-Path $outResolved 'wf_stability_ext_*.json'
        $extMetaFile = Get-ChildItem -Path $extMetaPattern -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($extMetaFile) {
            $runMeta.files += $extMetaFile.FullName
            try {
                $extData = Get-Content -Path $extMetaFile.FullName -Raw | ConvertFrom-Json
                $runMeta.validation.strict = $extData.strict_criteria
                $runMeta.validation.meta_json = $extMetaFile.FullName
                $runMeta.validation.raw_csv = $extData.raw_csv
                $runMeta.validation.summary_csv = $extData.summary_csv
                $runMeta.validation.final_csv = $extData.final_csv
                $runMeta.validation.candidates = $extData.candidates
                $runMeta.validation.final_picks = $extData.final_picks
                if ($extData.raw_csv) { $runMeta.files += $extData.raw_csv }
                if ($extData.summary_csv) { $runMeta.files += $extData.summary_csv }
                if ($extData.final_csv) { $runMeta.files += $extData.final_csv }
            } catch {
                Write-Host "Failed to read validation meta: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }

        if ($DryRun) {
            Write-Host "`nDry run: final CSV not generated." -ForegroundColor DarkGray
        } else {
            $finalPattern = Join-Path $outResolved 'final_candidates_*.csv'
            $finalCsv = Get-ChildItem -Path $finalPattern -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            if ($finalCsv) {
                Write-Host ("Final candidate CSV: {0}" -f $finalCsv.FullName) -ForegroundColor Green
                $runMeta.validation.final_csv = $finalCsv.FullName
                $runMeta.files += $finalCsv.FullName
            } else {
                Write-Host "Final candidate CSV was not produced." -ForegroundColor Yellow
            }
        }

        if ($Pack) {
            if ($DryRun) {
                Write-Host "Commit gate: -Pack cannot be used with -DryRun." -ForegroundColor Red
                $commitGate.status = 'failed'
                $commitGate.reason = 'DryRun prevents pack generation.'
                $commitGate.passed = $false
                $exitCode = 1
            } elseif (-not $EquityStart -or -not $EquityEnd) {
                Write-Host "Commit gate: specify both -EquityStart and -EquityEnd." -ForegroundColor Red
                $commitGate.status = 'failed'
                $commitGate.reason = 'EquityStart/EquityEnd not provided.'
                $commitGate.passed = $false
                $exitCode = 1
            } elseif (-not $finalCsv) {
                Write-Host "Commit gate: final_candidates CSV missing, cannot generate pack." -ForegroundColor Red
                $commitGate.status = 'failed'
                $commitGate.reason = 'final_candidates CSV unavailable.'
                $commitGate.passed = $false
                $exitCode = 1
            } else {
                $packArgs = @(
                    'tools/extended_backtest.py',
                    '--candidates', $finalCsv.FullName,
                    '--equity-start', $EquityStart,
                    '--equity-end', $EquityEnd,
                    '--out', $outResolved,
                    '--pack-ts', $runTimestamp
                )
                $packInvoke = Invoke-PythonCommand -Python $python -Arguments $packArgs -LogFile $LogFile -CaptureOutput -SuppressHostOutput
                if ($packInvoke.ExitCode -ne 0) {
                    Write-Host "extended_backtest failed. Commit gate aborted." -ForegroundColor Red
                    $commitGate.status = 'failed'
                    $commitGate.reason = "extended_backtest exited with code $($packInvoke.ExitCode)"
                    $commitGate.passed = $false
                    $exitCode = 1
                } else {
                    $packJsonRaw = $packInvoke.Output
                    try {
                        $packParsed = $packJsonRaw | ConvertFrom-Json
                    } catch {
                        Write-Host "Failed to parse extended_backtest output." -ForegroundColor Red
                        $commitGate.status = 'failed'
                        $commitGate.reason = 'extended_backtest output parsing failed.'
                        $commitGate.passed = $false
                        $exitCode = 1
                    }
                }

                if ($packParsed -and $packParsed.pack) {
                    $runMeta.pack = $packParsed.pack
                    if ($packParsed.extended_results) {
                        $runMeta.extended_results = $packParsed.extended_results
                    }

                    $packNode = $packParsed.pack
                    foreach ($extra in @($packNode.readme, $packNode.zip, $packNode.run_meta, $packNode.summary_csv)) {
                        if ($extra) { $runMeta.files += $extra }
                    }
                    if ($packNode.files_included) {
                        foreach ($name in $packNode.files_included) {
                            $candidatePath = Join-Path $outResolved $name
                            if (Test-Path $candidatePath) { $runMeta.files += $candidatePath }
                        }
                    }

                    if ($packNode.zip) {
                        Write-Host ("Results pack generated: {0}" -f $packNode.zip) -ForegroundColor Green
                    }

                    $gitInfo = $packNode.git
                    $commitRecommend = $packNode.commit_recommendation
                    $commitPassed = $true
                    if ($gitInfo -and $gitInfo.dirty -eq $true) { $commitPassed = $false }

                    $commitGate.status = if ($commitPassed) { 'passed' } else { 'failed' }
                    $commitGate.reason = $commitRecommend
                    $commitGate.passed = $commitPassed
                    if ($gitInfo) { $commitGate.git = $gitInfo }

                    if ($commitPassed) {
                        Write-Host "Commit gate passed: working tree clean." -ForegroundColor Green
                    } else {
                        Write-Host ("Commit gate failed: {0}" -f $commitRecommend) -ForegroundColor Red
                        if ($gitInfo -and $gitInfo.status_sample) {
                            Write-Host ("Dirty files snapshot: {0}" -f ($gitInfo.status_sample -join ', ')) -ForegroundColor Red
                        }
                        $exitCode = 1
                    }
                } elseif ($Pack) {
                    if (-not ($commitGate -is [System.Collections.Specialized.OrderedDictionary])) { $commitGate = [ordered]@{} }
                    if (-not $commitGate.Contains('status') -or $commitGate.status -ne 'failed') {
                        $commitGate.status = 'failed'
                        $commitGate.reason = 'Pack information missing in extended_backtest output.'
                        $commitGate.passed = $false
                        $exitCode = 1
                    }
                }
            }
        } else {
            $commitGate.status = 'not_requested'
            $commitGate.reason = 'Pack not requested'
            $commitGate.passed = $null
        }
    }
    if (-not ($commitGate -is [System.Collections.Specialized.OrderedDictionary])) { $commitGate = [ordered]@{} }
    if (-not $commitGate.Contains('status')) {
        if ($Pack) {
            $commitGate.status = 'failed'
            $commitGate.reason = 'Commit gate result unavailable.'
            $commitGate.passed = $false
            $exitCode = 1
        } else {
            $commitGate.status = 'not_requested'
            $commitGate.reason = 'Pack not requested'
            $commitGate.passed = $null
        }
    }

    $runMeta.commit_gate = $commitGate
    Write-RunMeta -Path $runMetaPath -Meta $runMeta
}
catch {
    try { Write-RunMeta -Path $runMetaPath -Meta $runMeta } catch {}
    throw
}
finally {
    Pop-Location
}
exit $exitCode
