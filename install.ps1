# Usage: run from the assignment work folder (current directory):
#   powershell -ExecutionPolicy Bypass -File "<kit path>\install.ps1"
# Rule: never overwrite files the platform already placed.
# Keep this file ASCII only (Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI).
$ErrorActionPreference = 'Continue'
$Kit = $PSScriptRoot
# Process working directory: what git sees, literal (no wildcard or provider quirks).
$Dest = [IO.Directory]::GetCurrentDirectory()
# PowerShell may have resolved a folder like [a] as a wildcard at startup. Pin its location (used as
# git's working directory) to the literal folder.
Set-Location -LiteralPath $Dest
$Placed = @()
$NFail = 0
$Utf8 = New-Object Text.UTF8Encoding($false)
$env:LC_ALL = 'C'   # this process only: English git messages so they can be matched

# Run git, never throw. Output lines go to the pipeline, exit code lands in $script:rc.
function G {
    $o = & git @args 2>&1 | ForEach-Object { "$_" }
    $script:rc = $LASTEXITCODE
    $o
}
function CopyTree([string]$src, [string]$dst) {
    $null = [IO.Directory]::CreateDirectory($dst)
    foreach ($f in [IO.Directory]::GetFiles($src)) { [IO.File]::Copy($f, [IO.Path]::Combine($dst, [IO.Path]::GetFileName($f))) }
    foreach ($d in [IO.Directory]::GetDirectories($src)) { CopyTree $d ([IO.Path]::Combine($dst, [IO.Path]::GetFileName($d))) }
}
# Copy a file or folder into the work folder. $rel uses forward slashes (also the git path).
function Put([string]$src, [string]$rel, [string]$label) {
    $dst = [IO.Path]::Combine($Dest, ($rel -replace '/', '\'))
    try {
        $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($dst))
        if ([IO.Directory]::Exists($src)) { CopyTree $src $dst } else { [IO.File]::Copy($src, $dst) }
        $script:Placed += $rel
        Write-Host "[copy] $label"
    } catch {
        $script:NFail++
        Write-Host "[fail] $label not installed: $($_.Exception.Message)"
    }
}

# 0) Is git usable? Without it files are still copied and git steps are skipped.
$Git = [bool](Get-Command git -CommandType Application -ErrorAction SilentlyContinue)
if (-not $Git) {
    Write-Host '[git] git was not found on PATH. Files will be copied; baseline and commit are skipped. A human should install Git for Windows and commit by hand'
}

# 0b) Repository check and baseline of pre-existing hidden untracked paths (home-folder dotfiles etc.)
if ($Git) {
    $out = @(G rev-parse --git-dir)
    if ($script:rc -ne 0) {
        $msg = ($out -join ' ')
        if ($msg -match 'not a git repository') {
            $null = G init -q
            if ($script:rc -eq 0) { Write-Host '[git] no repository, ran git init' }
            else { $Git = $false; Write-Host '[git] git init failed. Git steps skipped. Report to a human' }
        } elseif ($msg -match 'dubious ownership') {
            $Git = $false
            Write-Host '[git] git refuses this repository (dubious ownership / safe.directory). Git steps skipped. A human must fix the ownership setting, then commit by hand'
        } else {
            $Git = $false
            Write-Host "[git] git rev-parse failed: $($out | Select-Object -First 1). Git steps skipped. Report to a human"
        }
    }
}
if (-not $Git) {
    Write-Host '[baseline] no usable repository, not recorded'
} else {
    $cdup = (G rev-parse --show-cdup) -join ''
    if ($script:rc -ne 0) {
        Write-Host '[baseline] could not locate repository root, not recorded'
    } elseif ($cdup -ne '') {
        # A parent repository (e.g. a home folder under git) must not receive the install commit.
        $Git = $false
        Write-Host '[git] work folder is inside a parent repository, not its root. Files are installed; baseline and commit skipped. If this folder should be its own repository: git init, then git add AGENTS.md .codex/agents .agents/skills, then git commit. Do not run this installer again for that'
    } elseif (-not (Test-Path -LiteralPath "$Dest\.cofa_baseline")) {
        $prev = [Console]::OutputEncoding
        try { [Console]::OutputEncoding = $Utf8 } catch { }
        $lines = @(G -c core.quotepath=off status --porcelain -unormal |
            Where-Object { $_.StartsWith('?? ') } |
            ForEach-Object { $_.Substring(3) -replace '^"', '' -replace '"$', '' } |
            Where-Object { $_.StartsWith('.') })
        try { [Console]::OutputEncoding = $prev } catch { }
        $text = ''
        if ($lines.Count -gt 0) { $text = ($lines -join "`n") + "`n" }
        try {
            [IO.File]::WriteAllText("$Dest\.cofa_baseline", $text, $Utf8)
            Write-Host "[baseline] recorded $($lines.Count) hidden untracked path(s) (.cofa_baseline, do not edit)"
        } catch {
            $NFail++
            Write-Host "[fail] .cofa_baseline not written: $($_.Exception.Message)"
        }
    }
}

# 1) AGENTS.md: copy if missing, else append below platform content when the kit rules are absent
$kitAgents = "$Kit\AGENTS.md"
$destAgents = "$Dest\AGENTS.md"
if (Test-Path -LiteralPath $destAgents -PathType Leaf) {
    try {
        $marker = ([IO.File]::ReadAllText($kitAgents, [Text.Encoding]::UTF8) -split "`r?`n")[0].TrimStart([char]0xFEFF)
        $cur = [IO.File]::ReadAllText($destAgents, [Text.Encoding]::UTF8)
        if ($cur.IndexOf($marker, [StringComparison]::Ordinal) -lt 0) {
            if ($Git) {
                $null = G ls-files --error-unmatch -- AGENTS.md
                if ($script:rc -eq 0) {
                    $st = @(G status --porcelain -- AGENTS.md)
                    if ($st.Count -gt 0) { Write-Host '[warn] tracked AGENTS.md has uncommitted changes. The install commit includes AGENTS.md, so those changes will be committed too' }
                }
            }
            # byte-level append keeps existing bytes (and any BOM) untouched; one write
            $kb = [IO.File]::ReadAllBytes($kitAgents)
            $off = 0; if ($kb.Length -ge 3 -and $kb[0] -eq 0xEF -and $kb[1] -eq 0xBB -and $kb[2] -eq 0xBF) { $off = 3 }
            $nl = $Utf8.GetBytes("`n`n")
            $buf = New-Object byte[] ($nl.Length + $kb.Length - $off)
            [Array]::Copy($nl, 0, $buf, 0, $nl.Length)
            [Array]::Copy($kb, $off, $buf, $nl.Length, $kb.Length - $off)
            $fs = New-Object IO.FileStream($destAgents, [IO.FileMode]::Append, [IO.FileAccess]::Write)
            try { $fs.Write($buf, 0, $buf.Length) } finally { $fs.Close() }
            $Placed += 'AGENTS.md'; Write-Host '[append] added rules below existing AGENTS.md'
        } else {
            Write-Host '[skip] AGENTS.md already has the rules'
        }
    } catch {
        $NFail++
        Write-Host "[fail] AGENTS.md rules not appended (read-only or locked?): $($_.Exception.Message)"
    }
} else {
    Put $kitAgents 'AGENTS.md' 'AGENTS.md'
}

# 2) Subagent definitions: skip same-name files
foreach ($f in @(Get-ChildItem -LiteralPath "$Kit\.codex\agents" -Filter *.toml -File)) {
    if (Test-Path -LiteralPath "$Dest\.codex\agents\$($f.Name)") { Write-Host "[skip] .codex/agents/$($f.Name) exists" }
    else { Put $f.FullName ".codex/agents/$($f.Name)" ".codex/agents/$($f.Name)" }
}

# 3) Project config.toml: never touch an existing one
if (Test-Path -LiteralPath "$Dest\.codex\config.toml") {
    Write-Host '[skip] .codex/config.toml exists, left unchanged. Nesting limit is covered by AGENTS.md rules'
} else {
    Put "$Kit\.codex\config.toml" '.codex/config.toml' '.codex/config.toml'
}

# 4) Skills: skip same-name folders
foreach ($d in @(Get-ChildItem -LiteralPath "$Kit\.agents\skills" -Directory)) {
    if (Test-Path -LiteralPath "$Dest\.agents\skills\$($d.Name)") { Write-Host "[skip] skill $($d.Name) exists" }
    else { Put $d.FullName ".agents/skills/$($d.Name)" "skill $($d.Name)" }
}

# 5) Install-record commit: only paths this run placed (plus .cofa_baseline). Failures never stop the install.
if ($Git) {
    $null = G config user.name
    if ($script:rc -ne 0) { $null = G config user.name 'candidate' }
    $null = G config user.email
    if ($script:rc -ne 0) { $null = G config user.email 'candidate@local' }
    $paths = @($Placed)
    if (Test-Path -LiteralPath "$Dest\.cofa_baseline") { $paths += '.cofa_baseline' }
    $added = @()
    foreach ($p in $paths) {
        $o = @(G add -- $p)
        if ($script:rc -eq 0) { $added += $p }
        else {
            $why = ($o | Where-Object { $_ -and $_ -notmatch '^hint:' } | Select-Object -First 2) -join ' '
            if (($o -join ' ') -match 'ignored') { $why = 'ignored by a .gitignore rule' }
            Write-Host "[git] not added: $p ($why). File is installed but not committed. Do not work around it; a human decides"
        }
    }
    if ($added.Count -eq 0) {
        Write-Host '[git] nothing to commit'
    } else {
        $null = G diff --cached --quiet -- @added
        if ($script:rc -eq 0) {
            Write-Host '[git] nothing to commit'
        } else {
            $null = G commit -q -m 'Add work rules, subagents, and skill config (source: public repo MIIXmix/cofa-kit)' -- @added
            if ($script:rc -eq 0) { Write-Host "[git] install commit done ($($added.Count) path(s); other staged files untouched)" }
            else { Write-Host '[git] commit failed (.git read-only etc.). Files are installed. Do not work around it; a human should commit' }
        }
    }
}

Write-Host ''
if (-not [IO.File]::Exists($destAgents)) { $NFail++; Write-Host '[fail] AGENTS.md is not in the work folder' }
if ($NFail -gt 0) {
    Write-Host "[result] INCOMPLETE: $NFail problem(s) above. Report them as they are; do not say the install succeeded"
    exit 1
}
Write-Host 'Next: 1) quit Codex (/quit) and start it again (codex)'
Write-Host "      2) ask 'what is rule 2?' to confirm AGENTS.md is loaded"
Write-Host '      3) (optional) check the model ID with /model, then uncomment the model lines in .codex/agents/*.toml'
exit 0
