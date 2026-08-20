################################################################################
# ZeroPoint Cluster Connection Verification & Activation
# Run this on ZERO-DEV to verify and establish cluster connection
################################################################################

param(
    [switch]$Verify,
    [switch]$Connect,
    [switch]$Full
)

$HeadNodeIP = "192.168.0.140"
$RayPort = 6379
$RayClientPort = 10001
$McpPort = 8765
$IdentityPort = 8766
$PythonPath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) ".venv\Scripts\python.exe"

# Helper functions
function OK  ($m) { Write-Host "  [OK]  $m" -ForegroundColor Green  }
function INF ($m) { Write-Host "  [-->] $m" -ForegroundColor Cyan   }
function WRN ($m) { Write-Host "  [WRN] $m" -ForegroundColor Yellow }
function ERR ($m) { Write-Host "  [ERR] $m" -ForegroundColor Red    }

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║      ZeroPoint Cluster Connection Verification Tool           ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Default to verify if no switches
if (-not ($Verify -or $Connect -or $Full)) {
    $Verify = $true
}

if ($Verify) {
    Write-Host "CLUSTER CONNECTIVITY CHECK" -ForegroundColor Yellow
    Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host ""
    
    Write-Host "Testing connection to ZERO-FLD (192.168.0.140)..." -ForegroundColor Cyan
    Write-Host ""
    
    # Test Ray Head
    Write-Host "1️⃣  Ray Head Port (6379):" -ForegroundColor White
    try {
        $result = Test-NetConnection -ComputerName $HeadNodeIP -Port $RayPort -WarningAction SilentlyContinue
        if ($result.TcpTestSucceeded) {
            OK "OPEN - Ray head is reachable ✓"
            $rayOpen = $true
        } else {
            ERR "CLOSED - Ray head not reachable"
            $rayOpen = $false
        }
    } catch {
        ERR "ERROR - $($_.Exception.Message)"
        $rayOpen = $false
    }
    
    Write-Host ""
    
    # Test MCP Server
    Write-Host "2️⃣  MCP Server Port (8765):" -ForegroundColor White
    try {
        $result = Test-NetConnection -ComputerName $HeadNodeIP -Port $McpPort -WarningAction SilentlyContinue
        if ($result.TcpTestSucceeded) {
            OK "OPEN - MCP server is reachable ✓"
            $mcpOpen = $true
        } else {
            ERR "CLOSED - MCP server not reachable"
            $mcpOpen = $false
        }
    } catch {
        ERR "ERROR - $($_.Exception.Message)"
        $mcpOpen = $false
    }
    
    Write-Host ""
    
    # Test Identity Service
    Write-Host "3️⃣  Identity Service (8766):" -ForegroundColor White
    try {
        $result = Test-NetConnection -ComputerName $HeadNodeIP -Port $IdentityPort -WarningAction SilentlyContinue
        if ($result.TcpTestSucceeded) {
            OK "OPEN - Identity service is reachable ✓"
            $idOpen = $true
        } else {
            ERR "CLOSED - Identity service not reachable"
            $idOpen = $false
        }
    } catch {
        ERR "ERROR - $($_.Exception.Message)"
        $idOpen = $false
    }
    
    Write-Host ""
    Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host ""
    
    if ($rayOpen -and $mcpOpen -and $idOpen) {
        OK "All services reachable - ZERO-FLD is running! ✓"
        Write-Host ""
        Write-Host "🎉 Cluster is ACTIVE and ready for connection!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Next step: Run with -Connect flag to initialize Ray" -ForegroundColor Cyan
        Write-Host "  .\verify_cluster_connection.ps1 -Connect" -ForegroundColor Gray
    } elseif ($idOpen) {
        WRN "Identity service is reachable, but Ray/MCP are not"
        WRN "ZERO-FLD may be starting or Ray head not fully initialized"
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Cyan
        Write-Host "  1. Wait 15-20 seconds for ZERO-FLD to fully start" -ForegroundColor Gray
        Write-Host "  2. Run verification again:" -ForegroundColor Gray
        Write-Host "     .\verify_cluster_connection.ps1 -Verify" -ForegroundColor Gray
    } else {
        ERR "ZERO-FLD is not responding"
        Write-Host ""
        Write-Host "Troubleshooting:" -ForegroundColor Yellow
        Write-Host "  1. Verify ZERO-FLD machine is running" -ForegroundColor Gray
        Write-Host "  2. Start head node on ZERO-FLD:" -ForegroundColor Gray
        Write-Host "     .\activate_cluster_head.ps1 -Activate" -ForegroundColor Gray
        Write-Host "  3. Wait 15-20 seconds for startup" -ForegroundColor Gray
        Write-Host "  4. Run this verification again" -ForegroundColor Gray
    }
    
    exit 0
}

if ($Connect) {
    Write-Host "INITIALIZING CLUSTER CONNECTION" -ForegroundColor Yellow
    Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host ""
    
    # First verify connection
    INF "Verifying connectivity to ZERO-FLD..."
    try {
        $result = Test-NetConnection -ComputerName $HeadNodeIP -Port $RayPort -WarningAction SilentlyContinue
        if (-not $result.TcpTestSucceeded) {
            ERR "Cannot reach Ray head on $HeadNodeIP`:$RayPort"
            ERR "Please start ZERO-FLD head node first:"
            ERR "  .\activate_cluster_head.ps1 -Activate"
            exit 1
        }
    } catch {
        ERR "Connection test failed: $($_.Exception.Message)"
        exit 1
    }
    
    OK "ZERO-FLD is reachable ✓"
    Write-Host ""
    
    # Determine preferred Ray connection mode.
    $rayClientReachable = $false
    try {
        $rayClientCheck = Test-NetConnection -ComputerName $HeadNodeIP -Port $RayClientPort -WarningAction SilentlyContinue
        $rayClientReachable = [bool]$rayClientCheck.TcpTestSucceeded
    } catch {
        $rayClientReachable = $false
    }

    # Set Ray address
    INF "Setting Ray cluster address..."
    if ($rayClientReachable) {
        $env:RAY_ADDRESS = "ray://$HeadNodeIP`:$RayClientPort"
        OK "RAY_ADDRESS set to Ray Client: $env:RAY_ADDRESS"
    } else {
        $env:RAY_ADDRESS = "$HeadNodeIP`:$RayPort"
        WRN "Ray Client port $RayClientPort is not reachable; using direct address: $env:RAY_ADDRESS"
    }
    Write-Host ""
    $pythonRayAddress = $env:RAY_ADDRESS
    
    # Initialize Ray connection
    INF "Connecting to Ray cluster..."

    $rayImportCheck = & $PythonPath -c "import ray; print('RAY_OK')" 2>&1
    if ($rayImportCheck -notlike "*RAY_OK*") {
        WRN "Local Ray client is not usable in this Python environment."
        WRN "Falling back to network-verified mode (head is reachable, RAY_ADDRESS is set)."
        Write-Host ""
        Write-Host "Details:" -ForegroundColor Yellow
        ($rayImportCheck -split "`n") | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        Write-Host ""
        Write-Host "To enable full Ray client attach on this node, recreate the venv with Python 3.11 and reinstall deps." -ForegroundColor Yellow
        exit 0
    }
    
    $rayTest = & $PythonPath -c @"
import ray
try:
    ray.init(address='${pythonRayAddress}', ignore_reinit_error=True)
    print('CONNECTED')
    nodes = ray.nodes()
    print(f'NODES:{len(nodes)}')
    for node in nodes:
        print(f"  - Node: {node['NodeID'][:8]}... (Alive: {node['Alive']})")
    resources = ray.cluster_resources()
    print(f'RESOURCES:{resources}')
except Exception as e:
    print(f'ERROR:{str(e)}')
"@ 2>&1
    
    if ($rayTest -like "*CONNECTED*") {
        OK "Successfully connected to Ray cluster! ✓"
        Write-Host ""
        
        # Show cluster info
        foreach ($line in $rayTest -split "`n") {
            if ($line -like "NODES:*") {
                $nodeCount = $line -replace "NODES:", ""
                OK "Cluster has $nodeCount node(s)"
            }
            if ($line -like "  - Node:*") {
                Write-Host "  $line" -ForegroundColor Gray
            }
            if ($line -like "RESOURCES:*") {
                Write-Host "  Cluster Resources: $($line -replace 'RESOURCES:', '')" -ForegroundColor Gray
            }
        }
        
        Write-Host ""
        Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Green
        Write-Host "✓ CLUSTER CONNECTION ESTABLISHED!" -ForegroundColor Green
        Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Green
        Write-Host ""
        Write-Host "ZERO-DEV is now connected to ZERO-FLD cluster" -ForegroundColor Green
        Write-Host "Distributed task execution is available" -ForegroundColor Green
    } else {
        ERR "Failed to connect to Ray cluster"
        Write-Host ""
        Write-Host "Error details:" -ForegroundColor Yellow
        $rayTest | ForEach-Object { if ($_ -like "*ERROR:*") { Write-Host "  $_" -ForegroundColor Red } }
        if (-not $rayClientReachable) {
            Write-Host ""
            WRN "Ray Client port $RayClientPort on ZERO-FLD is not reachable."
            WRN "On ZERO-FLD, restart head with Ray Client enabled and verify port $RayClientPort is listening."
        }
        exit 1
    }
    
    exit 0
}

if ($Full) {
    Write-Host "FULL CLUSTER ACTIVATION" -ForegroundColor Yellow
    Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host ""
    
    Write-Host "This will verify connectivity and establish cluster connection." -ForegroundColor Cyan
    Write-Host ""
    
    # Step 1: Verify
    & $PSCommandPath -Verify
    
    Write-Host ""
    
    # Check if Ray is reachable
    try {
        $result = Test-NetConnection -ComputerName $HeadNodeIP -Port $RayPort -WarningAction SilentlyContinue
        if ($result.TcpTestSucceeded) {
            Write-Host "Proceeding to connect..." -ForegroundColor Cyan
            Write-Host ""
            
            # Step 2: Connect
            & $PSCommandPath -Connect
        } else {
            ERR "Ray head is not reachable - cannot proceed"
            ERR "Start ZERO-FLD head node first"
            exit 1
        }
    } catch {
        ERR "Error during verification: $($_.Exception.Message)"
        exit 1
    }
    
    exit 0
}

# Show help
Write-Host "USAGE:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Verify connectivity:" -ForegroundColor White
Write-Host "    .\verify_cluster_connection.ps1 -Verify" -ForegroundColor Gray
Write-Host ""
Write-Host "  Initialize connection:" -ForegroundColor White
Write-Host "    .\verify_cluster_connection.ps1 -Connect" -ForegroundColor Gray
Write-Host ""
Write-Host "  Full activation (verify + connect):" -ForegroundColor White
Write-Host "    .\verify_cluster_connection.ps1 -Full" -ForegroundColor Gray
Write-Host ""
