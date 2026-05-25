# Mnemosyne Engine — Windows install (Doc 16 §2.2). Run by the NSIS installer.
$ErrorActionPreference = "Stop"
$engine = "$env:PROGRAMFILES\Mnemosyne\mnemosyne-engine.exe"

New-Service -Name "MnemosyneEngine" `
    -BinaryPathName "$engine --port 7432" `
    -DisplayName "Mnemosyne Memory Engine" `
    -StartupType Automatic `
    -Description "Local AI memory engine for Project Mnemosyne"

Start-Service MnemosyneEngine

New-NetFirewallRule -DisplayName "Mnemosyne Engine" `
    -Direction Inbound -LocalPort 7432 -Protocol TCP `
    -Action Allow -RemoteAddress 127.0.0.1 -ErrorAction SilentlyContinue

Write-Host "Mnemosyne Engine installed and running on localhost:7432"
