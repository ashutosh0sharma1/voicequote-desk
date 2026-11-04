$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$voiceQuoteSynth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voiceQuoteSynth.Rate = -1
$voiceQuoteCases = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'fixtures.json') -Raw | ConvertFrom-Json
foreach ($voiceQuoteCase in $voiceQuoteCases) {
    $voiceQuoteOutput = Join-Path $PSScriptRoot ('samples\' + $voiceQuoteCase.id + '.wav')
    $voiceQuoteSynth.SetOutputToWaveFile($voiceQuoteOutput)
    $voiceQuoteSynth.Speak($voiceQuoteCase.script)
    $voiceQuoteSynth.SetOutputToNull()
    Write-Output ('Synthetic WAV generated: ' + $voiceQuoteCase.id)
}
$voiceQuoteSynth.Dispose()
