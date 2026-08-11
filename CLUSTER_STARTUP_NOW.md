# 🚀 CLUSTER STARTUP GUIDE

## ✅ Pre-Flight Checklist (Already Complete)

- ✅ ZERO-FLD has sophisticated modules (control_plane, osint, pentest, it_support, ray_actors, service)
- ✅ ZERO-DEV has all modules synced
- ✅ Requirements merged and installed on ZERO-DEV
- ✅ Cluster scripts deployed to both machines
- ✅ Network connectivity verified

---

## 🎯 STARTUP SEQUENCE (CRITICAL ORDER)

### ⚠️ IMPORTANT: Start Backend (ZERO-FLD) First!

The backend must start BEFORE the frontend can connect. This is the orchestrator.

---

## STEP 1️⃣: Start ZERO-FLD (Backend/Head Node) on Lenovo IdeaPad 5

**Go to: ZERO-FLD (Lenovo IdeaPad 5) machine**

Open PowerShell and run:

```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# This starts Ray head + MCP servers on the backend
.\dev_start.ps1 -RayHead
```

**Expected output (wait 15-20 seconds):**
```
[OK] Ray head node started at 127.0.0.1:6379
[OK] MCP server running on ws://localhost:8765/mcp
[OK] Identity service on port 8766
[OK] ZeroPoint is running!
```

✅ **LEAVE THIS RUNNING** — Do NOT close this window

---

## STEP 2️⃣: Start ZERO-DEV (Frontend/Worker) on HP Envy

**Go to: ZERO-DEV (HP Envy) machine**

Open a NEW PowerShell window and run:

```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# This starts MCP servers and connects to ZERO-FLD cluster
.\dev_start.ps1

# (regular startup, not -RayHead)
```

**Expected output (wait 10 seconds):**
```
[OK] MCP server running on ws://localhost:8765/mcp
[OK] Identity service connecting to cluster...
[OK] Connected to Ray head at 192.168.0.140:6379
[OK] ZeroPoint is running!
```

✅ **LEAVE THIS RUNNING** — Do NOT close this window

---

## STEP 3️⃣: Verify Cluster Connection

**On ZERO-DEV**, open ANOTHER PowerShell window and run:

```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# Verify network connectivity to ZERO-FLD
.\verify_cluster_connection.ps1 -Verify

# Should show:
#   ✅ Port 6379 (Ray) - OPEN
#   ✅ Port 8765 (MCP) - OPEN  
#   ✅ Port 8766 (Identity) - OPEN
```

Then connect:

```powershell
# Establish cluster connection
.\verify_cluster_connection.ps1 -Connect

# Should show:
#   ✅ Connected to cluster!
#   ✅ Found 2 nodes:
#       - ZERO-FLD (Head)
#       - ZERO-DEV (Worker)
```

---

## STEP 4️⃣: Verify Full Cluster Status

Check the cluster is fully operational:

```powershell
# On ZERO-DEV, get cluster status
.\verify_cluster_connection.ps1 -Status

# Should show all systems operational
```

---

## 🎯 How It Works Now

Once both machines are running:

### Request Flow:
1. **You ask Copilot something** on ZERO-DEV (HP Envy)
2. **ZERO-DEV checks** if it's a local tool → runs locally (fast)
3. **If remote capability needed** → sends to ZERO-FLD
4. **ZERO-FLD processes** using:
   - 🔍 OSINT module (research & investigation)
   - 🛡️ Pentest module (security testing)
   - 🤖 Control plane (AI orchestration)
   - 🎯 IT Support agents (system recovery)
   - ⚡ Ray distributed computing (parallel processing)
5. **Result returns** to ZERO-DEV
6. **You see answer** in VS Code

### Example Tasks:
- **Fast** (local): Read file on ZERO-DEV → 1ms
- **Powerful** (remote): OSINT investigation → Sent to backend → 5-30s
- **Distributed** (cluster): Analyze system across multiple nodes → Results aggregated

---

## 📊 Cluster Architecture (Now Running)

```
┌─────────────────────────────────┐
│   ZERO-DEV (HP Envy)            │
│   ├─ MCP Server (8765)          │
│   ├─ Identity Service (8766)    │
│   ├─ Local tools                │
│   └─ Ray Worker (connected)     │
└──────────────┬──────────────────┘
               │
         (Network via Ray)
               │
┌──────────────▼──────────────────┐
│   ZERO-FLD (Lenovo IdeaPad 5)   │
│   ├─ MCP Server (8765)          │
│   ├─ Identity Service (8766)    │
│   ├─ Ray Head (6379)            │
│   ├─ Control Plane              │
│   ├─ OSINT Module               │
│   ├─ Pentest Module             │
│   ├─ IT Support Agents          │
│   └─ Ray Actors (distribute)    │
└─────────────────────────────────┘
```

---

## ⚡ Available Tools After Startup

### On ZERO-DEV (Local):
- Filesystem operations
- Web tools (fetch, search)
- Android/ADB tools
- Local system commands

### Via ZERO-FLD (Remote/Powerful):
- OSINT investigations
- Penetration testing tools
- System analysis & recovery
- Distributed task execution
- AI orchestration

### All Available to You:
- In GitHub Copilot Chat (on ZERO-DEV)
- Via VS Code tool picker
- Natural language requests to Claude/Copilot

---

## 🔧 Troubleshooting During Startup

### ZERO-FLD Won't Start:
```powershell
# Kill any stuck Ray processes
Get-Process | Where-Object { $_.Name -like "*ray*" } | Stop-Process -Force

# Restart
.\dev_start.ps1 -RayHead
```

### ZERO-DEV Can't Connect:
```powershell
# Check firewall allows port 6379
Test-NetConnection -ComputerName 192.168.0.140 -Port 6379

# If blocked, enable port 6379 in Windows Firewall
New-NetFirewallRule -DisplayName "Ray Cluster" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 6379
```

### Cluster Says "Not Connected":
```powershell
# Wait 30 seconds after ZERO-FLD starts (it needs time to initialize)
# Then run verify again
.\verify_cluster_connection.ps1 -Connect
```

---

## 📝 Command Reference

### Quick Start (After First Time):
```powershell
# On ZERO-FLD:
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\dev_start.ps1 -RayHead

# On ZERO-DEV:
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\dev_start.ps1
```

### Check Status Anytime:
```powershell
# On ZERO-DEV:
.\verify_cluster_connection.ps1 -Status
```

### View Logs:
```powershell
# On ZERO-DEV:
Get-Content .\server.log -Tail 20

# On ZERO-FLD:
Get-Content Z:\Downloads\zeropoint-mcp\server.log -Tail 20
```

### Stop Servers:
```powershell
# Press Ctrl+C in the running PowerShell windows
# OR close the windows
```

---

## ✅ You're Now Ready!

Your two-machine AI cluster is ready to:
- **Pen test** systems locally
- **Analyze** and recover systems
- **Run complex investigations** across both machines
- **Maximize AI model performance** with distributed computing
- **Automate IT tasks** with no external dependencies

**Get the best of local AI cluster computing!** 🚀
