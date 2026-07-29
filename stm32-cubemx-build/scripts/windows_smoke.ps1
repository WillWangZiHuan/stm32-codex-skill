[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Manual,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$BoardProfile,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Plan,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Mcu,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputDir,

    [ValidateNotNullOrEmpty()]
    [string]$ProjectName = "stm32_windows_smoke",

    [ValidateNotNullOrEmpty()]
    [string]$ModuleName = "windows_smoke",

    [string]$Pack,
    [string]$CubeMX,
    [string]$CubeIDE,
    [ValidateNotNullOrEmpty()]
    [string]$Python = "python",
    [int]$Jobs = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RequiredFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Value -PathType Leaf)) {
        throw "$Label must be an existing file: $Value"
    }
    return (Resolve-Path -LiteralPath $Value).Path
}

function Resolve-OrCreateOutputDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if (Test-Path -LiteralPath $Value) {
        if (-not (Test-Path -LiteralPath $Value -PathType Container)) {
            throw "OutputDir must be a directory: $Value"
        }
    }
    else {
        New-Item -ItemType Directory -Path $Value -ErrorAction Stop | Out-Null
    }
    return (Resolve-Path -LiteralPath $Value).Path
}

function Invoke-Stm32Skill {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$SkillArguments
    )

    Write-Host ("STM32 Skill: " + ($SkillArguments -join " "))
    & $Python $skillScript @SkillArguments
    if ($LASTEXITCODE -ne 0) {
        throw "STM32 Skill command failed with exit code $LASTEXITCODE."
    }
}

try {
    if ($ProjectName -notmatch '^[A-Za-z][A-Za-z0-9_-]*$') {
        throw "Use a ProjectName that starts with a letter and contains letters, numbers, underscores, or hyphens."
    }
    if ($ModuleName -notmatch '^[a-z][a-z0-9_]*$') {
        throw "Use a ModuleName that starts with a lowercase letter and contains lowercase letters, numbers, or underscores."
    }
    if ($Jobs -lt 0) {
        throw "Jobs must be zero or a positive integer."
    }

    $hasPack = -not [string]::IsNullOrWhiteSpace($Pack)
    if ($hasPack -and $Pack -notmatch '^[a-z][a-z0-9-]*$') {
        throw "Use a Pack name that starts with a lowercase letter and contains lowercase letters, numbers, or hyphens."
    }
    $null = Get-Command -Name $Python -ErrorAction Stop

    $skillScript = Join-Path -Path $PSScriptRoot -ChildPath "stm32_cube.py"
    if (-not (Test-Path -LiteralPath $skillScript -PathType Leaf)) {
        throw "Could not find stm32_cube.py beside this script: $skillScript"
    }

    $manualPath = Resolve-RequiredFile -Value $Manual -Label "Manual"
    $profilePath = Resolve-RequiredFile -Value $BoardProfile -Label "BoardProfile"
    $planPath = Resolve-RequiredFile -Value $Plan -Label "Plan"
    $outputPath = Resolve-OrCreateOutputDirectory -Value $OutputDir
    $projectDir = Join-Path -Path $outputPath -ChildPath $ProjectName
    if (Test-Path -LiteralPath $projectDir) {
        throw "Project directory already exists: $projectDir. Choose a new ProjectName or OutputDir."
    }

    $toolArguments = @()
    if (-not [string]::IsNullOrWhiteSpace($CubeMX)) {
        $toolArguments += @("--cubemx", $CubeMX)
    }
    if (-not [string]::IsNullOrWhiteSpace($CubeIDE)) {
        $toolArguments += @("--cubeide", $CubeIDE)
    }

    Invoke-Stm32Skill -SkillArguments ($toolArguments + @("doctor", "--strict"))
    Invoke-Stm32Skill -SkillArguments (
        $toolArguments + @(
            "generate",
            "--mcu", $Mcu,
            "--name", $ProjectName,
            "--output-dir", $outputPath,
            "--board-profile", $profilePath,
            "--manual", $manualPath,
            "--plan", $planPath
        )
    )

    $moduleArguments = $toolArguments + @("module", "--project-dir", $projectDir, "--name", $ModuleName)
    if ($hasPack) {
        $moduleArguments += @("--pack", $Pack)
    }
    Invoke-Stm32Skill -SkillArguments $moduleArguments
    Invoke-Stm32Skill -SkillArguments (
        $toolArguments + @("integrate", "--project-dir", $projectDir, "--name", $ModuleName)
    )

    $buildArguments = $toolArguments + @("build", "--project-dir", $projectDir)
    if ($Jobs -gt 0) {
        $buildArguments += @("--jobs", $Jobs.ToString())
    }
    Invoke-Stm32Skill -SkillArguments $buildArguments

    Write-Host "WINDOWS_SMOKE_PASS"
    Write-Host "Generated and compiled project: $projectDir"
    Write-Host "Generation and compilation completed. Hardware flashing, debugging, and measurement continue in a separate board run."
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
