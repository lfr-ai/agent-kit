[CmdletBinding(SupportsShouldProcess)]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Persistent checkout registration requires Windows.'
}

$checkout = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
foreach ($required in @('catalog.json', 'apm.yml', 'PROJECT.md')) {
    if (-not (Test-Path -LiteralPath (Join-Path $checkout $required) -PathType Leaf)) {
        throw "Not an agent-kit source checkout: missing $required."
    }
}

$current = [Environment]::GetEnvironmentVariable(
    'AGENT_KIT_DIR',
    [EnvironmentVariableTarget]::User
)
if ($current -eq $checkout) {
    Write-Output "AGENT_KIT_DIR is already registered: $checkout"
    return
}

if ($PSCmdlet.ShouldProcess(
    "AGENT_KIT_DIR=$checkout (previous: $current)",
    'Set the Windows user environment variable'
)) {
    [Environment]::SetEnvironmentVariable(
        'AGENT_KIT_DIR',
        $checkout,
        [EnvironmentVariableTarget]::User
    )
    Write-Output "Registered AGENT_KIT_DIR=$checkout"
    Write-Output 'Fully restart VS Code and terminals to inherit the new user environment.'
}
