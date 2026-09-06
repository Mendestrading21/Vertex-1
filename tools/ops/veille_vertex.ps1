<#
tools/ops/veille_vertex.ps1 — chien de garde LOCAL de l'instance de travail Vertex.

Pourquoi : le 2026-09-06, l'instance relancée à 07:17 s'est arrêtée trois
minutes plus tard sans traceback ni événement Windows ; personne ne l'a vu
avant une heure. Ce script ne fait qu'une chose : sonder /healthz, et quand
l'instance ne répond plus ET que plus rien n'écoute sur son port, la relancer
depuis le dépôt. Il ne touche jamais TWS, n'ouvre aucune session courtier
lui-même (Vertex le fait, en lecture seule), ne stocke aucun secret (le code
d'accès vit dans .env, lu par Vertex).

Ce script N'EST PAS installé automatiquement : l'inscrire dans une tâche
planifiée est une décision humaine (voir VERTEX_RUNBOOK.md §1). Lancement
manuel :

    powershell -NoProfile -ExecutionPolicy Bypass -File tools\ops\veille_vertex.ps1

Paramètres : -Port 5002, -IntervalleS 60, -EchecsAvantRelance 3,
-Journal "%LOCALAPPDATA%\Vertex\veille.log" (borné à 2 000 lignes).
#>
param(
    [int]$Port = 5002,
    [int]$IntervalleS = 60,
    [int]$EchecsAvantRelance = 3,
    [string]$Journal = (Join-Path $env:LOCALAPPDATA "Vertex\veille.log")
)

$ErrorActionPreference = 'Continue'
$Depot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $Depot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $Python)) { $Python = Join-Path $Depot ".venv\Scripts\python.exe" }

function Ecrire([string]$ligne) {
    $dir = Split-Path $Journal
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $Journal -Value "$ts $ligne" -Encoding utf8
    # journal borné : jamais plus de 2 000 lignes.
    #
    #  `Get-Content` SANS `-Encoding` lit avec la page de codes ANSI de Windows,
    #  alors que la ligne vient d'être écrite en UTF-8 : au 2001e passage, la
    #  troncature relisait « démarrée » comme « dÃ©marrÃ©e » et le RÉÉCRIVAIT
    #  ainsi. Le journal se corrompait donc tout seul, une fois, tard, et sur
    #  le seul fichier qu'un humain vient lire après un incident.
    try {
        $lignes = Get-Content $Journal -Encoding utf8 -ErrorAction Stop
        if ($lignes.Count -gt 2000) {
            $lignes[-2000..-1] | Set-Content -Path $Journal -Encoding utf8
        }
    } catch {}
}

function Sain() {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 8
        return ($r.status -eq 'ok')
    } catch { return $false }
}

function Ecoute() {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.OwningProcess } else { return $null }
}

function Relancer() {
    if (-not (Test-Path $Python)) { Ecrire "RELANCE IMPOSSIBLE : $Python absent (créer .venv, voir Lancer_VERTEX.bat)"; return }
    $p = Start-Process -FilePath $Python -ArgumentList "-m", "vertex" -WorkingDirectory $Depot -WindowStyle Hidden -PassThru
    Ecrire "RELANCE : pid $($p.Id) depuis $Depot"
}

Ecrire "veille démarrée : port $Port, sonde toutes les $IntervalleS s, relance après $EchecsAvantRelance échecs"
$echecs = 0
while ($true) {
    if (Sain) {
        if ($echecs -gt 0) { Ecrire "rétabli après $echecs échec(s)" }
        $echecs = 0
    } else {
        $echecs += 1
        $pid = Ecoute
        Ecrire "échec $echecs/$EchecsAvantRelance (port écouté par : $(if ($pid) { $pid } else { 'personne' }))"
        # Un processus qui écoute encore mais ne répond pas peut être en train
        # de scanner : on ne le tue jamais ; on ne relance que si le port est libre.
        if ($echecs -ge $EchecsAvantRelance -and -not $pid) {
            Relancer
            $echecs = 0
            Start-Sleep -Seconds 60
        }
    }
    Start-Sleep -Seconds $IntervalleS
}
