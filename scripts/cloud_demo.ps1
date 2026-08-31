# cloud_demo.ps1 — drive the deployed Cloud Run SOW-TaskMaster via its REST API
# ------------------------------------------------------------------------------
# The python CLI (main.py) runs locally against data/cases/. The deployed Cloud Run
# app only exposes the FastAPI web API. This script maps the CLI scenarios onto
# the live HTTP endpoints so you can run them against the judge URL.
#
# Usage:
#   # Sample £45K request -> parks at awaiting_signature (webhook mode)
#   .\scripts\cloud_demo.ps1 -Action start
#
#   # High-value £120K request -> executive approval path (2 approvers)
#   .\scripts\cloud_demo.ps1 -Action start -Request high
#
#   # Invalid request -> validation fails -> case is BLOCKED for HITL
#   .\scripts\cloud_demo.ps1 -Action start -Request invalid
#
#   # Arbitrary custom request text:
#   .\scripts\cloud_demo.ps1 -Action start -RequestText "Project: Foo`nCustomer: Bar`nBudget: 30000 GBP`nTimeline: 12 weeks"
#
#   # List all cases / stats  |  # One case detail (incl. timeline)
#   .\scripts\cloud_demo.ps1 -Action cases
#   .\scripts\cloud_demo.ps1 -Action case -CaseId SOW-XXXXXXXX
#
#   # HITL decision on a blocked case:
#   .\scripts\cloud_demo.ps1 -Action resolve -CaseId SOW-XXXXXXXX -Decision approve
#   .\scripts\cloud_demo.ps1 -Action resolve -CaseId SOW-XXXXXXXX -Decision reject -Notes "not for us"
#
#   # Simulate DocuSign webhook (only valid while case is awaiting_signature):
#   .\scripts\cloud_demo.ps1 -Action sign -CaseId SOW-XXXXXXXX
#
#   # Natural-language query over all cases:
#   .\scripts\cloud_demo.ps1 -Action query -Question "where is SOW-XXXXXXXX right now?"
# ------------------------------------------------------------------------------

param(
  [string]$BaseUrl   = "https://sow-taskmaster-122458747029.us-central1.run.app",
  [ValidateSet("health","start","cases","case","sign","resolve","query")]
  [string]$Action    = "start",
  [string]$CaseId    = "",
  [ValidateSet("sample","high","invalid")]
  [string]$Request   = "sample",
  [string]$RequestText = "",
  [ValidateSet("approve","override","resend","reject")]
  [string]$Decision  = "approve",
  [string]$Notes     = "",
  [string]$Question  = "how many cases are complete?",
  [int]$TimeoutSec   = 90
)

$ErrorActionPreference = "Stop"

$SampleRequest = @"
Project: Cloud Migration and Infrastructure Modernisation
Customer: Acme Corporation
Budget: 45000 GBP
Timeline: 16 weeks
Scope: Migrate on-premise infrastructure to AWS, including database migration and staff training.
"@

$HighRequest = @"
Project: Enterprise Data Platform Modernisation
Customer: Globex Industries
Budget: 120000 GBP
Timeline: 24 weeks
Scope: Build a unified data platform on Google Cloud: data lake, warehouse, ETL pipelines, governance.
"@

$InvalidRequest = @"
Project: Rushed Deal
Customer: Test Corp
Budget: 200 GBP
Timeline: 200 weeks
Scope: Impossibly fast delivery with almost no budget.
"@

function Invoke-Api {
  param([string]$Method, [string]$Path, $Body = $null)
  $uri = "$BaseUrl$Path"
  $allArgs = @{ Method = $Method; Uri = $uri; TimeoutSec = $TimeoutSec }
  if ($null -ne $Body -and $Method -ne "GET") {
    $allArgs.ContentType = "application/json"
    $allArgs.Body = ($Body | ConvertTo-Json -Compress)
  }
  try {
    return Invoke-RestMethod @allArgs
  }
  catch {
    $resp = $_.Exception.Response
    $detail = ""
    if ($resp) {
      try {
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $detail = $reader.ReadToEnd()
      } catch {}
    }
    Write-Host "ERROR: $($_.Exception.Message) $detail" -ForegroundColor Red
    exit 1
  }
}
switch ($Action) {
  "health" {
    $r = Invoke-Api -Method GET -Path "/api/health"
    $r | ConvertTo-Json -Compress
  }
  "start" {
    $text = if ($RequestText) { $RequestText }
            elseif ($Request -eq "high")   { $HighRequest }
            elseif ($Request -eq "invalid"){ $InvalidRequest }
            else { $SampleRequest }
    $r = Invoke-Api -Method POST -Path "/api/cases/start" -Body @{ request_text = $text }
    Write-Host "Started $($r.case_id) -> status=$($r.status) stage=$($r.stage)" -ForegroundColor Cyan
    if ($r.status -eq "awaiting_signature") {
      Write-Host "Next: sign it ->" -NoNewline; Write-Host " .\scripts\cloud_demo.ps1 -Action sign -CaseId $($r.case_id)" -ForegroundColor Green
    } elseif ($r.status -eq "blocked") {
      Write-Host "Next: resolve it ->" -NoNewline; Write-Host " .\scripts\cloud_demo.ps1 -Action resolve -CaseId $($r.case_id) -Decision approve" -ForegroundColor Green
    }
  }
  "cases" {
    $r = Invoke-Api -Method GET -Path "/api/cases"
    Write-Host "Total: $($r.cases.Count) case(s)  Stats: $($r.stats | ConvertTo-Json -Compress)" -ForegroundColor Cyan
    $r.cases | ForEach-Object { "{0}  {1,-24} {2,-8} {3}" -f $_.case_id, $_.project_title, $_.current_stage, $_.status }
  }
  "case" {
    if (-not $CaseId) { Write-Host "Provide -CaseId" -ForegroundColor Red; exit 1 }
    $r = Invoke-Api -Method GET -Path "/api/cases/$CaseId"
    Write-Host "$($r.case_id)  $($r.project_title)  stage=$($r.current_stage) status=$($r.status) signed=$($r.signed_at)" -ForegroundColor Cyan
    if ($r.escalated_to_human) { Write-Host "  HITL: $($r.escalation_reason)  (decision: $($r.decision_id))" -ForegroundColor Yellow }
    Write-Host "  agent actions: $($r.timeline.Count)"
    $r.timeline | Select-Object -Last 8 | ForEach-Object { "  - [$($_.stage)] $($_.agent_name): $($_.action)" }
  }
  "sign" {
    if (-not $CaseId) { Write-Host "Provide -CaseId" -ForegroundColor Red; exit 1 }
    $r = Invoke-Api -Method POST -Path "/api/webhooks/esign/$CaseId"
    Write-Host "Webhook $($r.case_id) -> status=$($r.status)" -ForegroundColor Green
  }
  "resolve" {
    if (-not $CaseId) { Write-Host "Provide -CaseId" -ForegroundColor Red; exit 1 }
    $r = Invoke-Api -Method POST -Path "/api/cases/$CaseId/resolve" -Body @{ decision = $Decision; notes = $Notes }
    Write-Host "Resolved $($r.case_id) -> status=$($r.status) stage=$($r.stage)" -ForegroundColor Green
    if ($r.status -eq "awaiting_signature") {
      Write-Host "Next: sign it ->" -NoNewline; Write-Host " .\scripts\cloud_demo.ps1 -Action sign -CaseId $($r.case_id)" -ForegroundColor Green
    }
  }
  "query" {
    $r = Invoke-Api -Method POST -Path "/api/query" -Body @{ question = $Question }
    Write-Host "Q: $Question" -ForegroundColor Cyan
    Write-Host "A: $($r.answer)"
  }
}