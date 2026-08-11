# 🏗️ CLUSTER SETUP — STEP-BY-STEP WITH GUIDANCE

## Your Architecture

```
ZERO-DEV (HP Envy - Frontend/Workstation)
    ↓ makes requests to
ZERO-FLD (Lenovo IdeaPad 5 - Backend/Orchestrator)
    ↑ receives requests, returns results
```

---

## PHASE 1: Local Copy Setup on Backend (ZERO-FLD)

**Goal:** Move ZERO-FLD from network drive (Z:\) to local drive (C:\)

### Step 1A: On ZERO-FLD machine
Open PowerShell as Administrator and run:

```powershell
# First, check if C:\Users\zeroi\Downloads exists
Test-Path "C:\Users\zeroi\Downloads"

# If not, create it
New-Item -ItemType Directory -Path "C:\Users\zeroi\Downloads" -Force

# Now copy from Z:\ to C:\
# (This will take 5-10 minutes depending on connection speed)
Copy-Item -Path "Z:\Downloads\zeropoint-mcp" -Destination "C:\Users\zeroi\Downloads\zeropoint-mcp" -Recurse -Force

# Verify it worked
Test-Path "C:\Users\zeroi\Downloads\zeropoint-mcp"  # Should show TRUE
```

**What this does:** Creates a complete LOCAL copy on ZERO-FLD so it doesn't depend on network drive

---

## PHASE 2: Sync Sophisticated Modules to Frontend (ZERO-DEV)

**Goal:** Get ZERO-FLD's advanced modules to ZERO-DEV so your frontend is complete

### Step 2A: From ZERO-DEV, copy the advanced modules:

```powershell
# On ZERO-DEV, navigate to repo
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# Copy the advanced modules from ZERO-FLD
# These modules are sophisticated and should be available on frontend too

# Module 1: Control Plane (AI orchestration)
Copy-Item -Path "Z:\Downloads\zeropoint-mcp\zeropoint\control_plane" `
  -Destination ".\zeropoint\control_plane" -Recurse -Force

# Module 2: OSINT (Open Source Intelligence)
Copy-Item -Path "Z:\Downloads\zeropoint-mcp\zeropoint\osint" `
  -Destination ".\zeropoint\osint" -Recurse -Force

# Module 3: Pentest (Penetration Testing)
Copy-Item -Path "Z:\Downloads\zeropoint-mcp\zeropoint\pentest" `
  -Destination ".\zeropoint\pentest" -Recurse -Force

# Module 4: IT Support
Copy-Item -Path "Z:\Downloads\zeropoint-mcp\zeropoint\it_support" `
  -Destination ".\zeropoint\it_support" -Recurse -Force

# Module 5: Ray Actors (Distributed compute)
Copy-Item -Path "Z:\Downloads\zeropoint-mcp\zeropoint\ray_actors" `
  -Destination ".\zeropoint\ray_actors" -Recurse -Force

# Module 6: Service directory (supervision/monitoring)
Copy-Item -Path "Z:\Downloads\zeropoint-mcp\service" `
  -Destination ".\service" -Recurse -Force

# Verify all copied
dir .\zeropoint\control_plane
dir .\zeropoint\osint
dir .\zeropoint\pentest
dir .\zeropoint\it_support
dir .\zeropoint\ray_actors
dir .\service
# All should return folders with content
```

**What this does:** Brings all the sophisticated analysis modules to your frontend workstation

---

## PHASE 3: Merge Dependencies

**Goal:** Make sure both machines have all required Python packages

### Step 3A: Update requirements.txt to include everything

On ZERO-DEV, check what's in ZERO-FLD's requirements:

```powershell
# See what ZERO-FLD needs
Get-Content "Z:\Downloads\zeropoint-mcp\requirements.txt"

# Compare with ZERO-DEV's version
Get-Content "C:\Users\zeroi\Downloads\zeropoint-mcp\requirements.txt"
```

If ZERO-FLD has more/different packages, merge them:

```powershell
# Copy ZERO-FLD's requirements to ZERO-DEV (use the more complete version)
Copy-Item -Path "Z:\Downloads\zeropoint-mcp\requirements.txt" `
  -Destination "C:\Users\zeroi\Downloads\zeropoint-mcp\requirements.txt" -Force

# Then reinstall on ZERO-DEV to get all dependencies
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt --upgrade
```

**What this does:** Makes sure both machines have Ray, OSINT tools, pentest tools, etc.

---

## PHASE 4: Sync Cluster Scripts to Backend

**Goal:** Copy my cluster management scripts to ZERO-FLD

### Step 4A: On ZERO-DEV, copy the cluster scripts to ZERO-FLD:

```powershell
# These are the scripts I created for managing the cluster
Copy-Item -Path ".\activate_cluster_head.ps1" `
  -Destination "Z:\Downloads\zeropoint-mcp\activate_cluster_head.ps1" -Force

Copy-Item -Path ".\verify_cluster_connection.ps1" `
  -Destination "Z:\Downloads\zeropoint-mcp\verify_cluster_connection.ps1" -Force

Copy-Item -Path ".\deploy_repo.ps1" `
  -Destination "Z:\Downloads\zeropoint-mcp\deploy_repo.ps1" -Force

# Also copy documentation
Copy-Item -Path ".\CLUSTER_SETUP_GUIDE.md" `
  -Destination "Z:\Downloads\zeropoint-mcp\CLUSTER_SETUP_GUIDE.md" -Force

Copy-Item -Path ".\ACTIVATION_PROCEDURE.md" `
  -Destination "Z:\Downloads\zeropoint-mcp\ACTIVATION_PROCEDURE.md" -Force
```

---

## PHASE 5: Start the Cluster (In Order!)

### IMPORTANT: Must start BACKEND first, then FRONTEND

**Step 5A: On ZERO-FLD (Backend), start the head node:**

```powershell
# Switch to the LOCAL copy (not Z:\)
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# Start with Ray head (this makes it the orchestrator)
.\dev_start.ps1 -RayHead

# Wait 15-20 seconds for full startup
# You should see:
#   [OK] Ray head started at 127.0.0.1:6379
#   [OK] MCP server running on ws://localhost:8765/mcp
#   [OK] Identity service on port 8766
```

**Step 5B: On ZERO-DEV (Frontend), connect to the cluster:**

```powershell
# On your HP Envy
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# Verify you can reach ZERO-FLD
.\verify_cluster_connection.ps1 -Verify

# Should show all ports OPEN (6379, 8765, 8766)
# Then connect
.\verify_cluster_connection.ps1 -Connect

# Wait 5 seconds
# Should say: "✅ Connected to cluster!"
```

---

## PHASE 6: Verify Cluster is Working

```powershell
# On ZERO-DEV (frontend), check that you see both nodes
.\verify_cluster_connection.ps1 -Status

# Should show:
#   Node 1: ZERO-FLD (Head) - 192.168.0.140:6379
#   Node 2: ZERO-DEV (Worker) - localhost:8765
#   Status: CONNECTED ✓
```

---

## How It Works Once Running

### Request Flow:
1. **You** (on ZERO-DEV/HP Envy) ask Copilot a question
2. **ZERO-DEV** checks: Do I have this tool? 
   - Yes → Run locally (fast)
   - No → Send to ZERO-FLD
3. **ZERO-FLD** (Lenovo backend) runs complex analysis using:
   - Control plane (AI orchestration)
   - OSINT module (research)
   - Pentest module (security testing)
   - Ray actors (distributed processing)
4. **Result** comes back to ZERO-DEV
5. **You** see answer in VS Code

### Example Scenarios:
- **Local tool** (fast): Read a file on ZERO-DEV → Done in milliseconds
- **Remote tool** (powerful): Run OSINT investigation → Sent to ZERO-FLD → Uses sophisticated analysis → Results back
- **Distributed task**: Large analysis → ZERO-FLD splits across Ray workers → Returns aggregated result

---

## Troubleshooting During Setup

### If ZERO-FLD fails to start:
```powershell
# Check if port 6379 is already in use
Test-NetConnection -ComputerName 127.0.0.1 -Port 6379

# Kill any old Ray processes
Get-Process | Where-Object { $_.Name -like "*ray*" } | Stop-Process -Force

# Try starting again
.\dev_start.ps1 -RayHead
```

### If ZERO-DEV can't reach ZERO-FLD:
```powershell
# Verify network connection
Test-NetConnection -ComputerName 192.168.0.140 -Port 6379

# Check firewall
# Make sure Windows Firewall allows port 6379

# Restart both machines' network adapters if still failing
```

### If cluster connects but tools fail:
```powershell
# Reinstall dependencies
pip install -r requirements.txt --upgrade --force-reinstall

# Restart both servers
```

---

## Summary: What Each Machine Will Do

### ZERO-FLD (Lenovo - Backend/Head Node)
✅ Orchestrates the cluster
✅ Runs sophisticated analysis (OSINT, pentest, control plane)
✅ Manages Ray distributed computing
✅ Stores and processes complex data
✅ Always-on (you may want to autostart this)

### ZERO-DEV (HP Envy - Frontend/Worker)
✅ Your interactive workstation
✅ Where you use AI (GitHub Copilot, Claude)
✅ Local tools (filesystem, web, Android debugging)
✅ Connects to backend when you need advanced features
✅ Receives results from backend

---

## Next: Execute These Phases

I'm ready to help you run these steps. Should I:
1. Start with Phase 1 on ZERO-FLD (local copy setup)?
2. Walk you through each step interactively?
3. Run the PowerShell commands for you if you share the machine?

**Let me know where you want to start!** 🚀
