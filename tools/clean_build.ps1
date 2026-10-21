$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
foreach ($name in @('build', 'dist', 'installer')) {
    $target = [IO.Path]::GetFullPath((Join-Path $workspace $name))
    if ([IO.Path]::GetDirectoryName($target) -ne $workspace) {
        throw "Refusing to clean outside the FMEDA folder: $target"
    }
    if (Test-Path -LiteralPath $target) {
        if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Refusing to clean a linked directory: $target"
        }
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
