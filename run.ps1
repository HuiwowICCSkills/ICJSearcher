# Locate a Python that can run this skill, then hand off to the skill CLI.
$skillCandidates = @(
    (Join-Path $PSScriptRoot 'venv\Scripts\python.exe'),
    (Join-Path $PSScriptRoot 'venv/bin/python'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'),
    (Join-Path $env:USERPROFILE '.workbuddy\binaries\python\versions\3.13.12\python.exe')
)
$skillPathPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($skillPathPython) { $skillCandidates += $skillPathPython }
$skillPathPython3 = (Get-Command python3 -ErrorAction SilentlyContinue).Source
if ($skillPathPython3) { $skillCandidates += $skillPathPython3 }

$skillPython = $null
foreach ($skillCandidate in $skillCandidates) {
    if (-not $skillCandidate -or -not (Test-Path -LiteralPath $skillCandidate -PathType Leaf)) { continue }
    & $skillCandidate -c 'import requests, bs4' 2>$null
    if ($LASTEXITCODE -eq 0) { $skillPython = $skillCandidate; break }
}
if (-not $skillPython) {
    throw 'No Python with requests and beautifulsoup4 was found. Run: python -m pip install -r requirements.txt (or create venv/).'
}
$skillArguments = foreach ($skillArgument in $args) {
    if ($skillArgument -is [array]) { $skillArgument -join ',' } else { $skillArgument }
}
& $skillPython -X utf8 (Join-Path $PSScriptRoot 'scripts\icj_search.py') $skillArguments
exit $LASTEXITCODE

