# ZeroPoint Nexus Cluster Setup & Connection Guide

## Current Cluster Status Summary

### Your Two Machines:

| Machine | Role | Status | Purpose |
|---------|------|--------|---------|
| **ZERO-FLD** | HEAD (Server) | ⚠️ Not Running | Backend resources, Ray orchestrator |
| **ZERO-DEV** | WORKER (Workstation) | ✅ Running | Your workstation, local tools |

**Current Network State:**
- ✅ Identity Service (port 8766): REACHABLE
- ❌ Ray Head (port 6379): NOT REACHABLE
- ❌ MCP Server (port 8765): NOT REACHABLE

**Interpretation:** ZERO-FLD is either **not running** or **not accessible on the network**

---

## 🎯 Understanding the Architecture

### Your Assumption is **CORRECT** ✓

```
ZERO-DEV (This Machine)              ZERO-FLD (Other Machine)
────────────────────────            ──────────────────────
    Workstation                          Backend Server
    ┌──────────────┐                  ┌──────────────┐
    │ User Apps    │◄────────────────►│ Ray Head     │
    │ Local Tools  │  Cluster Network │ Shared       │
    │ 18 Tools     │  (TCP 6379)      │ Resources    │
    │ MCP Client   │                  │ MCP Master   │
    └──────────────┘                  └──────────────┘

When connected:
  - ZERO-DEV can offload tasks to ZERO-FLD
  - ZERO-FLD manages distributed execution
  - Both can share resources via Ray
```

---

## 🔗 How AIO (All-In-One) Local Access Works

### Local Tool Execution (What Works Now)
```
User Request
    ↓
MCP Server (localhost:8765)
    ↓
Tool Registry (18 tools)
    ├─ ADB Device Access
    ├─ Android Management
    ├─ File Operations
    └─ Other Local Tools
    ↓
Execute Locally
```

### Distributed Execution (When Connected)
```
User Request
    ↓
MCP Server (localhost:8765)
    ↓
Check Tool Location
    ├─ Local Tool? → Execute Here ✓
    └─ Remote Tool? → Send to Ray
        ↓
    Ray Client (this machine)
        ↓
    Ray Head (ZERO-FLD:6379)
        ↓
    Ray Worker (could be any node)
        ↓
    Execute on Appropriate Node
        ↓
    Return Results
```

---

## 🚀 What You Need to Do Now

### Phase 1: Start ZERO-FLD (Head Node)
On the **other machine (ZERO-FLD)**, you need to:

1. **Open PowerShell** on ZERO-FLD
2. **Navigate to zeropoint-mcp directory**
3. **Start the head node:**
   ```powershell
   cd C:\path\to\zeropoint-mcp
   .\dev_start.ps1 -RayHead
   ```

This will:
- Start Ray head node (localhost:6379)
- Start MCP server (localhost:8765)
- Start Identity service (localhost:8766)
- Make resources available to worker nodes

### Phase 2: Verify Connection from ZERO-DEV
After ZERO-FLD is running:

```powershell
# Test Ray connectivity
Test-NetConnection -ComputerName 192.168.0.140 -Port 6379

# You should see: TcpTestSucceeded: True ✓
```

### Phase 3: Verify Cluster Status
Once both running, check discovery:

```powershell
# This will show cluster topology
$env:RAY_ADDRESS = "192.168.0.140:6379"
python -c "import ray; ray.init(address='192.168.0.140:6379'); print(ray.cluster_resources())"
```

---

## 📊 Communication Flow Chart

### Before (Current State - Isolated)
```
ZERO-DEV                    ZERO-FLD
┌──────────┐               ┌──────────┐
│          │     BLOCKED   │          │
│ MCP: 8765├──────X───────►│ MCP: 8765│
│          │               │          │
│ Ray CLI  │     BLOCKED   │ Ray Head │
│          ├──────X───────►│          │
└──────────┘               └──────────┘

RESULT: Only local execution possible
```

### After (Connected - Distributed)
```
ZERO-DEV                    ZERO-FLD
┌──────────┐     OPEN      ┌──────────┐
│          │    (6379)     │          │
│ MCP: 8765├──────✓───────►│ MCP: 8765│
│          │               │          │
│ Ray CLI  │    TUNNELED   │ Ray Head │
│          ├──────✓───────►│          │
└──────────┘               └──────────┘

RESULT: Full cluster capabilities available
```

---

## 🔧 Detailed Setup Steps

### Step 1: On ZERO-FLD Machine
```powershell
# 1. Open PowerShell
# 2. Go to zeropoint-mcp directory
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# 3. Start with Ray head
.\dev_start.ps1 -RayHead

# 4. Wait for output showing:
#    [OK] MCP server started
#    [OK] Ray head initialized
```

### Step 2: Verify ZERO-FLD is Running
On ZERO-FLD, in a **new PowerShell window**:
```powershell
# Check if services are listening
netstat -ano | findstr "6379\|8765\|8766"

# Should show:
#   TCP    127.0.0.1:6379      LISTENING
#   TCP    127.0.0.1:8765      LISTENING
#   TCP    127.0.0.1:8766      LISTENING
```

### Step 3: Test from ZERO-DEV
Back on **ZERO-DEV**:
```powershell
# Test connectivity
Test-NetConnection -ComputerName 192.168.0.140 -Port 6379
Test-NetConnection -ComputerName 192.168.0.140 -Port 8765
Test-NetConnection -ComputerName 192.168.0.140 -Port 8766

# All should show: TcpTestSucceeded: True
```

### Step 4: Initialize Ray Connection on ZERO-DEV
```powershell
# Set Ray address
$env:RAY_ADDRESS = "192.168.0.140:6379"

# Test connection
python -c "import ray; ray.init(address='192.168.0.140:6379', ignore_reinit_error=True); print('Connected to cluster'); print(ray.cluster_resources())"
```

### Step 5: Verify Both Nodes Visible
```powershell
# This should show both nodes in the cluster
python -c "
import ray
ray.init(address='192.168.0.140:6379', ignore_reinit_error=True)
nodes = ray.nodes()
for node in nodes:
    print(f'Node: {node[\"NodeID\"]} - {node[\"Alive\"]}')"
```

---

## 🎓 How Tool Distribution Works

### Example: ADB Command

**If ADB is only on ZERO-DEV:**
```
User: "Execute ADB command"
  ↓
ZERO-DEV MCP checks registry
  ↓
"ADB is local" → Execute locally → Return result ✓
```

**If tool is only on ZERO-FLD:**
```
User: "Execute special tool"
  ↓
ZERO-DEV checks registry
  ↓
"Tool is on ZERO-FLD" → Send to Ray
  ↓
ZERO-FLD executes → Returns result ✓
```

**Mixed Scenario (Both Running Different Tools):**
```
ZERO-DEV:           ZERO-FLD:
- ADB               - GPU Processing
- Android Tools     - Data Analysis
- File Ops          - Backup/Archive
  ↓                   ↓
  └─── Ray Cluster ───┘
       (port 6379)
```

---

## ⚙️ Configuration Files Used

| File | Location | Purpose |
|------|----------|---------|
| `cluster_registry.json` | Both machines | Defines node topology |
| `governance.json` | Both machines | Policy & permissions |
| `mcp_server_config.yaml` | Both machines | MCP settings |
| Environment: `RAY_ADDRESS` | ZERO-DEV | Points to head node |

---

## ✅ Verification Checklist

- [ ] ZERO-FLD machine has zeropoint-mcp directory
- [ ] ZERO-FLD has Python venv with Ray installed
- [ ] ZERO-FLD: Run `.\dev_start.ps1 -RayHead`
- [ ] Wait 10-15 seconds for startup
- [ ] ZERO-DEV: Test connectivity to 192.168.0.140:6379
- [ ] Verify ports 6379, 8765, 8766 are open
- [ ] Set $env:RAY_ADDRESS = "192.168.0.140:6379"
- [ ] Test Ray cluster discovery
- [ ] Verify both nodes appear in cluster
- [ ] Check tool registry is merged across nodes

---

## 🆘 Troubleshooting

### Issue: "Connection refused" on port 6379
**Solution:** Start ZERO-FLD with Ray head
```powershell
.\dev_start.ps1 -RayHead
```

### Issue: "Network timeout"
**Solution:** Check firewall
```powershell
# Allow port 6379
netsh advfirewall firewall add rule name="Ray" dir=in action=allow protocol=tcp localport=6379

# Check if port is already listening on ZERO-FLD
netstat -ano | findstr "6379"
```

### Issue: Ray module import fails
**Solution:** Ensure proper dependencies
```powershell
# In venv on both machines:
pip install ray
pip install -e .  # Install zeropoint package
```

### Issue: Nodes see each other but tools don't sync
**Solution:** Restart MCP servers on both nodes
```powershell
.\dev_start.ps1 -Stop
Start-Sleep -Seconds 5
.\dev_start.ps1 -RayHead  # on ZERO-FLD
.\dev_start.ps1           # on ZERO-DEV
```

---

## 📞 Quick Reference

### Start Commands
```powershell
# On ZERO-FLD (Backend/Head)
.\dev_start.ps1 -RayHead

# On ZERO-DEV (Workstation/Worker)
.\dev_start.ps1

# Both should show: [OK] MCP server started
```

### Check Status
```powershell
# On either machine
.\manage_autostart.ps1 -Check

# Check connectivity from ZERO-DEV
Test-NetConnection -ComputerName 192.168.0.140 -Port 6379
```

### Stop Services
```powershell
.\dev_start.ps1 -Stop
```

### View Logs
```powershell
Get-Content server.log -Wait
```

---

## 🎯 Next Action

1. **Go to ZERO-FLD machine**
2. **Run:** `.\dev_start.ps1 -RayHead`
3. **Wait for:** `[OK] MCP server started`
4. **Come back to ZERO-DEV**
5. **Run:** `Test-NetConnection -ComputerName 192.168.0.140 -Port 6379`
6. **Report back:** Success or error

---

**Status:** Cluster configured, Ray head not running. Start ZERO-FLD to establish connection.
