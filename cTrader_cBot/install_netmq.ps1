# cTrader NetMQ Package Installer
# Automates NetMQ package download for cTrader cBot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "cTrader NetMQ Package Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if nuget.exe exists
$nugetPath = ".\nuget.exe"

if (-Not (Test-Path $nugetPath)) {
    Write-Host "[1/3] Downloading nuget.exe..." -ForegroundColor Yellow
    $nugetUrl = "https://dist.nuget.org/win-x86-commandline/latest/nuget.exe"

    try {
        Invoke-WebRequest -Uri $nugetUrl -OutFile $nugetPath
        Write-Host "✓ nuget.exe downloaded successfully" -ForegroundColor Green
    }
    catch {
        Write-Host "✗ Failed to download nuget.exe: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[1/3] nuget.exe already exists" -ForegroundColor Green
}

Write-Host ""

# Create packages directory
$packagesDir = ".\packages"
if (-Not (Test-Path $packagesDir)) {
    New-Item -ItemType Directory -Path $packagesDir | Out-Null
    Write-Host "[2/3] Created packages directory" -ForegroundColor Green
} else {
    Write-Host "[2/3] Packages directory exists" -ForegroundColor Green
}

Write-Host ""

# Install NetMQ package
Write-Host "[3/3] Installing NetMQ package..." -ForegroundColor Yellow

try {
    & $nugetPath install NetMQ -OutputDirectory $packagesDir -Version 4.0.1.13
    Write-Host "✓ NetMQ package installed successfully" -ForegroundColor Green
}
catch {
    Write-Host "✗ Failed to install NetMQ: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Open cTrader -> Automate -> New cBot" -ForegroundColor White
Write-Host "2. Click 'Manage References' -> 'Add Local File'" -ForegroundColor White
Write-Host "3. Navigate to:" -ForegroundColor White
Write-Host "   $packagesDir\NetMQ.4.0.1.13\lib\net47\NetMQ.dll" -ForegroundColor Cyan
Write-Host "4. Click 'OK' to add the reference" -ForegroundColor White
Write-Host ""
Write-Host "Or copy the DLL to cTrader's global packages folder:" -ForegroundColor Yellow
Write-Host "   %USERPROFILE%\Documents\cAlgo\Sources\Packages\" -ForegroundColor Cyan
Write-Host ""

# Optional: Show package contents
$netmqPackage = Get-ChildItem -Path $packagesDir -Filter "NetMQ.*" -Directory | Select-Object -First 1

if ($netmqPackage) {
    Write-Host "Package location:" -ForegroundColor Yellow
    Write-Host "   $($netmqPackage.FullName)" -ForegroundColor Cyan
    Write-Host ""

    $dllPath = Join-Path $netmqPackage.FullName "lib\net47\NetMQ.dll"
    if (Test-Path $dllPath) {
        Write-Host "NetMQ.dll found at:" -ForegroundColor Green
        Write-Host "   $dllPath" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
