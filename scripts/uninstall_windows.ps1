# Mnemosyne Engine — Windows uninstall (Doc 16 §8). Data preserved by default.
Stop-Service MnemosyneEngine -ErrorAction SilentlyContinue
sc.exe delete MnemosyneEngine 2>$null
Remove-Item "$env:PROGRAMFILES\Mnemosyne" -Recurse -Force -ErrorAction SilentlyContinue
Remove-NetFirewallRule -DisplayName "Mnemosyne Engine" -ErrorAction SilentlyContinue
Write-Host "Engine removed. Memory data preserved at $env:APPDATA\Mnemosyne\"
Write-Host "To delete all data: Remove-Item `"$env:APPDATA\Mnemosyne`" -Recurse -Force"
