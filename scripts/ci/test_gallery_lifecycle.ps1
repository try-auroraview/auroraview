param([string]$WorkflowScript, [string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$workflow = [scriptblock]::Create((Get-Content -LiteralPath $WorkflowScript -Raw))

# Execute the actual workflow body with no real processes, network, or pytest.
function Start-Process {
    if ($case.launch_fail) { throw 'synthetic launch failure' }
    $fakeProcess
}
function Start-Sleep {}
function Invoke-WebRequest {
    if ($case.exit_before_pytest) { $fakeProcess.HasExited = $true }
    [pscustomobject]@{ StatusCode = 200 }
}
function Get-Date {
    $script:dateCalls++
    if ($case.timeout -and $script:dateCalls -gt 1) { [DateTime]::UtcNow.AddSeconds(121) }
    else { [DateTime]::UtcNow }
}
function vx {
    $casesXml = '<testcase name="required" />'
    if ($case.all_skipped) { $casesXml = '<testcase name="required"><skipped /></testcase>' }
    if ($case.partial_skipped) { $casesXml += '<testcase name="other"><skipped /></testcase>' }
    if ($case.no_tests) { $casesXml = '' }
    "<testsuites><testsuite>$casesXml</testsuite></testsuites>" | Set-Content -LiteralPath 'test-results/gallery/junit.xml'
    if ($case.exit_during_pytest) { $fakeProcess.HasExited = $true }
    $global:LASTEXITCODE = $case.pytest_exit
}

$cases = @(
    @{ name = 'success'; pytest_exit = 0 },
    @{ name = 'early_exit'; pytest_exit = 0; exited = $true; error = '*exited before CDP*17*' },
    @{ name = 'cdp_timeout'; pytest_exit = 0; timeout = $true; error = '*CDP not ready after 120s*' },
    @{ name = 'pytest_failure'; pytest_exit = 7; error = '*CDP tests failed*7*' },
    @{ name = 'cleanup_failure'; pytest_exit = 0; kill_fail = $true; error = '*synthetic cleanup failure*' },
    @{ name = 'pytest_and_cleanup_failure'; pytest_exit = 7; kill_fail = $true; error = '*CDP tests failed*7*' },
    @{ name = 'launch_failure'; pytest_exit = 0; launch_fail = $true; error = '*synthetic launch failure*' },
    @{ name = 'all_skipped'; pytest_exit = 0; all_skipped = $true; error = '*coverage incomplete*1 skipped*' },
    @{ name = 'partial_skipped'; pytest_exit = 0; partial_skipped = $true; error = '*coverage incomplete*1 skipped*' },
    @{ name = 'no_tests'; pytest_exit = 0; no_tests = $true; error = '*coverage incomplete*0 collected*' },
    @{ name = 'exit_before_pytest'; pytest_exit = 0; exit_before_pytest = $true; error = '*exited before pytest*17*' },
    @{ name = 'exit_during_pytest'; pytest_exit = 0; exit_during_pytest = $true; error = '*exited during pytest*17*' },
    @{ name = 'exit_before_cleanup'; pytest_exit = 0; exit_before_cleanup = $true; error = '*exited before cleanup*17*' },
    @{ name = 'cleanup_timeout'; pytest_exit = 0; cleanup_timeout = $true; error = '*did not exit within 5s*' }
)
foreach ($case in $cases) {
    $directory = Join-Path $OutputDirectory $case.name
    $null = New-Item -ItemType Directory -Force (Join-Path $directory 'gallery/pack-output')
    Set-Content -LiteralPath (Join-Path $directory 'gallery/pack-output/auroraview-gallery.exe') -Value 'never executed'
    $fakeProcess = [pscustomobject]@{ Id = 424242; HasExited = [bool]$case.exited; ExitCode = 17; ThrowOnKill = [bool]$case.kill_fail; CleanupTimeout = [bool]$case.cleanup_timeout; ExitBeforeCleanup = [bool]$case.exit_before_cleanup; RefreshCount = 0 }
    $fakeProcess | Add-Member ScriptMethod Refresh {
        $this.RefreshCount++
        if ($this.ExitBeforeCleanup -and $this.RefreshCount -eq 4) { $this.HasExited = $true }
    }
    $fakeProcess | Add-Member ScriptMethod Kill { param($entireTree) if ($this.ThrowOnKill) { throw 'synthetic cleanup failure' } }
    $fakeProcess | Add-Member ScriptMethod WaitForExit {
        param($milliseconds)
        if ($milliseconds -ne 5000) { throw 'Cleanup wait must be bounded to 5s' }
        if ($this.CleanupTimeout) { return $false }
        $this.HasExited = $true
        $this.ExitCode = -1
        return $true
    }
    $script:dateCalls = 0
    $caught = $null
    Push-Location $directory
    try {
        try { & $workflow } catch { $caught = $_.Exception.Message }
        $state = Get-Content -LiteralPath 'test-results/gallery/process.json' -Raw | ConvertFrom-Json
        if ($case.error) {
            if ($caught -notlike $case.error) { throw "Unexpected failure in $($case.name): $caught" }
        } elseif ($caught) { throw "Unexpected failure in $($case.name): $caught" }
        if ($case.kill_fail -and -not $state.cleanup_error) { throw 'Cleanup error was not recorded' }
        if ($case.exited -and $state.exit_code -ne 17) { throw 'Natural exit code was not recorded' }
        if ($case.cleanup_timeout -and $state.has_exited) { throw 'Cleanup timeout was reported as exited' }
        if ($state.cleanup_forced -and -not $state.cleanup_error) {
            if (-not $state.has_exited -or $state.exit_code -ne -1) { throw 'Post-cleanup exit state was not read back' }
        }
        if ($case.name -eq 'success' -and ($state.stage -ne 'complete' -or $state.tests_collected -ne 1 -or $state.tests_skipped -ne 0)) { throw 'Successful lifecycle did not complete' }
        Write-Host "Passed offline lifecycle scenario: $($case.name)"
    } finally { Pop-Location }
}
