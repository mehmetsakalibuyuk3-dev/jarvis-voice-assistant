$env:OLLAMA_MAX_LOADED_MODELS = "2"
$env:OLLAMA_NUM_PARALLEL = "2"
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden -RedirectStandardOutput "NUL" -RedirectStandardError "NUL"
Start-Sleep -Seconds 6
$connected = Test-NetConnection -ComputerName 127.0.0.1 -Port 11434 -InformationLevel Quiet
if ($connected) { Write-Output "OLLAMA_OK" } else { Write-Output "OLLAMA_FAILED" }
