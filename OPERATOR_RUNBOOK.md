# ZeroPoint Operator Runbook
## Phase B - Copy/Paste Only Workflows

**Last Updated:** 2026-08-12  
**Audience:** Security operations center, device recovery technicians, authorized penetration testers

---

## 🎯 Quick Start: 60-Second Setup

```powershell
# 1. Open PowerShell as Administrator
# 2. Navigate to repo
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# 3. Verify cluster is ready (run this first, every day)
.\operator.ps1 -Mode verify

# 4. Run any workflow from the sections below (copy/paste entire line)
```

**Tip:** If step 3 fails, see [Troubleshooting](#troubleshooting) → "Cluster Connection Issues"

---

## 📋 Workflow Reference

### ✅ 1. Verify Cluster (Run First!)

**Purpose:** Check that ZERO-DEV ↔ ZERO-FLD connectivity is healthy.  
**Time:** ~10 seconds  
**Requirements:** ZERO-FLD must be powered on and services running

**Copy/Paste Command:**
```powershell
.\operator.ps1 -Mode verify
```

**Expected Output:**
```
[✓] Ray head reachable
[✓] MCP server reachable
[✓] Identity service reachable
[✓] Cluster is reachable and healthy.
```

**If it fails:** See [Troubleshooting](#troubleshooting)

---

### 🔍 2. Autonomous Pentest - Phase 1 (Recon)

**Purpose:** Automated network discovery, port scanning, service enumeration on target range.  
**Time:** 5-30 minutes (depending on range size and network latency)  
**Requirements:** 
- Target network is in authorized scope
- Network access from ZERO-FLD to target
- Cluster is healthy (run verify first)

**Preset Stages:** `nmap` → `service-identify` → `enum4linux` → `whatweb`

**Copy/Paste Command:**
```powershell
.\operator.ps1 -Mode pentest -TargetRange "192.168.0.0/24" -Scope "authorized-assessment-001" -PentestPhase phase1-recon
```

**Parameters Explained:**
- `-TargetRange`: CIDR notation (e.g., `10.0.0.0/16`, `192.168.1.100/32`)
- `-Scope`: Ticket/authorization reference (audit trail, required)
- `-PentestPhase`: `phase1-recon` | `phase2-exploit` | `phase1-2-full`

**Alternative: Phase 1 + Phase 2 (Full Pipeline)**
```powershell
.\operator.ps1 -Mode pentest -TargetRange "192.168.0.0/24" -Scope "authorized-assessment-001" -PentestPhase phase1-2-full
```

**Alternative: Phase 2 with Metasploit & Hashcat**
```powershell
.\operator.ps1 -Mode pentest `
  -TargetRange "192.168.0.0/24" `
  -Scope "authorized-assessment-001" `
  -PentestPhase phase2-exploit `
  -UseMetasploit `
  -UseHashcat `
  -ActorRole "security-lead"
```

**Expected Output:**
```
[→] Pentest Phase: phase1-recon
[→] Stages: nmap → service-identify → enum4linux → whatweb
[→] Payload: {...}
[✓] Pentest workflow submitted successfully.
```

**Then wait for results in logs** (see [Logs & Evidence](#logs--evidence))

---

### 🔓 3. Autonomous Device Recovery - Android

**Purpose:** Automated Android device detection, state analysis, unlock attempt, data extraction.  
**Time:** 2-15 minutes  
**Requirements:**
- Device is connected via USB to ZERO-FLD
- ADB bridge is functional
- Device is in bootloader or unlocked developer mode

**Preset Stages:** `adb-detect` → `device-state` → `unlock-attempt` → `data-extract`

**Copy/Paste Command:**
```powershell
.\operator.ps1 -Mode recovery -DeviceName "OnePlus-Test" -Scope "recovery-ticket-042"
```

**Parameters Explained:**
- `-DeviceName`: Friendly name for device (for logging/audit)
- `-Scope`: Recovery ticket reference (required for audit)
- `-DeviceType`: `android` (default) | `ios`

**Alternative: iOS Device Recovery**
```powershell
.\operator.ps1 -Mode recovery -DeviceName "iPhone-12" -Scope "recovery-ticket-043" -DeviceType ios
```

**Expected Output:**
```
[→] Device: OnePlus-Test (Type: android)
[→] Stages: adb-detect → device-state → unlock-attempt → data-extract
[✓] Recovery workflow submitted successfully.
```

---

### 📊 4. Analytics & Reporting

**Purpose:** Automated OSINT summarization, IoC extraction, alert triage.  
**Time:** 30 seconds - 2 minutes

#### 4a. Summarize OSINT Report

```powershell
.\operator.ps1 -Mode analytics -AnalysisType "summarize_osint" -InputFile "C:\path\to\osint_report.txt"
```

#### 4b. Extract IoCs (Indicators of Compromise)

```powershell
.\operator.ps1 -Mode analytics -AnalysisType "extract_iocs" -InputFile "C:\path\to\threat_report.txt"
```

#### 4c. Triage Security Alert

```powershell
.\operator.ps1 -Mode analytics -AnalysisType "triage_alert" -InputFile "C:\path\to\alert.json"
```

---

### 🔤 5. Quick Translation (Ollama Backend)

**Purpose:** Translate short text using Ollama LLM (Spanish in this example).  
**Time:** 5-15 seconds

**Copy/Paste Command:**
```powershell
.\operator.ps1 -Mode translate
```

---

### 6️⃣ List Available Task Presets

**Purpose:** See all available workflow templates and their stages.

**Copy/Paste Command:**
```powershell
.\operator.ps1 -Mode list-presets
```

**Output shows:**
- All pentest phases and their stages
- All recovery device types and stages
- Descriptions for each

---

## 🔍 Execution Modes

By default, the operator runner auto-detects the best execution mode:

- **`auto`** (Default): Try Ray Client first; fall back to Ray Direct if needed
- **`ray-client`**: Force distributed execution via Ray Client (recommended for cluster)
- **`ray-direct`**: Force direct Ray head connection (if Ray Client unavailable)
- **`local`**: Force local execution (debug only; bypasses cluster)

To force a specific mode:

```powershell
# Force Ray Client mode
.\operator.ps1 -Mode pentest -TargetRange "192.168.0.0/24" -Scope "test" -ExecutionMode ray-client

# Force local mode (debug)
.\operator.ps1 -Mode verify -ExecutionMode local
```

---

## 📁 Logs & Evidence

All task submissions generate timestamped logs:

**Location:** `C:\Users\zeroi\Downloads\zeropoint-mcp\logs\`

**Log Files:**
- `cluster_connection.log` — Connectivity checks
- `task_submissions.log` — All submitted tasks + payloads
- `autonomous_workflows.log` — Pentest/recovery execution logs
- `audit_trail.json` — Full audit trail (timestamps, scope, actor, actions)

**To view latest logs:**

```powershell
# Tail task submissions
Get-Content "C:\Users\zeroi\Downloads\zeropoint-mcp\logs\task_submissions.log" -Tail 50

# Tail autonomous workflows
Get-Content "C:\Users\zeroi\Downloads\zeropoint-mcp\logs\autonomous_workflows.log" -Tail 100

# View audit trail (pretty-printed)
$audit = Get-Content "C:\Users\zeroi\Downloads\zeropoint-mcp\logs\audit_trail.json" | ConvertFrom-Json
$audit | Format-Table -AutoSize | Out-Host -Paging
```

**To find a specific task by scope ID:**

```powershell
$logs = Get-Content "C:\Users\zeroi\Downloads\zeropoint-mcp\logs\audit_trail.json" | ConvertFrom-Json
$logs | Where-Object { $_.scope_id -eq "authorized-assessment-001" } | Format-List
```

---

## 🔐 Role-Based Access Control

Some workflows require specific actor roles:

- **`operator`** (Default): Basic operator, read-only pentest recon
- **`security-lead`**: Can enable Metasploit, Hashcat cracking
- **`admin`**: Full access to all tools and workflows

To specify a role:

```powershell
.\operator.ps1 -Mode pentest `
  -TargetRange "192.168.0.0/24" `
  -Scope "pentest-001" `
  -ActorRole "security-lead" `
  -UseMetasploit `
  -UseHashcat
```

**Note:** If you lack role permission, you'll see:
```
[✗] Access denied: actor role 'operator' not authorized for this workflow
```

Contact your administrator if you need elevated permissions.

---

## ⚠️ Troubleshooting

### **Cluster Connection Issues**

**Problem:** `verify` command fails with "Ray head not reachable"

**Diagnosis:**
```powershell
# Check ZERO-FLD is powered on and ping-able
Test-NetConnection -ComputerName 192.168.0.140 -Port 6379

# Check MCP server port
Test-NetConnection -ComputerName 192.168.0.140 -Port 8765
```

**Solution:**
1. **If 192.168.0.140 is not reachable:**
   - Power on ZERO-FLD (may be in sleep mode)
   - Check network cable or WiFi connection on ZERO-FLD
   - Verify ZERO-FLD and ZERO-DEV are on same subnet
   - Try: `ping 192.168.0.140` from ZERO-DEV

2. **If 192.168.0.140 is reachable but ports are closed:**
   - SSH into ZERO-FLD or access via desktop
   - Run: `.\dev_start.ps1 -RayHead` (restart cluster services)
   - Wait ~30 seconds for services to start
   - Re-run `.\operator.ps1 -Mode verify`

3. **If cluster verification passes but task submission fails:**
   - Check `logs\task_submissions.log` for detailed error
   - Verify your target network is reachable from ZERO-FLD
   - If Metasploit/Hashcat/John used: confirm tools are installed on ZERO-FLD

---

### **Task Hangs or Seems Stuck**

**Problem:** Task was submitted but no output for >5 minutes

**Diagnosis:**
```powershell
# Check logs for task progress
Get-Content "C:\Users\zeroi\Downloads\zeropoint-mcp\logs\autonomous_workflows.log" -Tail 100 | Where-Object { $_ -like "*in_progress*" }

# Check if network is reachable from ZERO-FLD
Test-NetConnection -ComputerName <target-ip> -Port 80 -WarningAction SilentlyContinue
```

**Solution:**
1. **If target network is unreachable:** Adjust `-TargetRange` or network setup
2. **If cluster logs show "Ray unavailable":** Restart Ray head (see above)
3. **If still stuck after 10 min:** Cancel task (`Ctrl+C`) and retry

---

### **Access Denied (Role Not Authorized)**

**Problem:** Task fails with "Access denied: actor role 'operator' not authorized"

**Solution:**
1. **Check your actor role:**
   ```powershell
   $userRole = "security-lead"  # Update to your actual role
   .\operator.ps1 -Mode pentest -TargetRange "..." -Scope "..." -ActorRole $userRole
   ```

2. **If unsure of your role:** Contact your security administrator

3. **To request elevated permissions:** Submit request to admin with business justification

---

### **Metasploit/Hashcat/John Not Found**

**Problem:** Pentest workflow fails with "Tool not found: metasploit"

**Solution:**
1. **Verify tools are installed on ZERO-FLD:**
   - SSH into ZERO-FLD
   - Run: `which msfconsole` (Metasploit)
   - Run: `which hashcat` (Hashcat)
   - Run: `which john` (John the Ripper)

2. **If tools not installed:** Contact infrastructure team to install them

3. **Workaround (Phase 1 only):** Run pentest without these tools:
   ```powershell
   .\operator.ps1 -Mode pentest -TargetRange "..." -Scope "..." -PentestPhase phase1-recon
   ```

---

### **Logs Directory Not Found**

**Problem:** "Logs directory does not exist"

**Solution:**
```powershell
# Create logs directory manually
New-Item -ItemType Directory -Path "C:\Users\zeroi\Downloads\zeropoint-mcp\logs" -Force

# Re-run workflow
.\operator.ps1 -Mode verify
```

---

## 🎓 Common Workflows By Job Function

### **Penetration Tester**

Daily workflow:
```powershell
# 1. Start of day - verify cluster
.\operator.ps1 -Mode verify

# 2. Run authorized assessment on internal network
.\operator.ps1 -Mode pentest `
  -TargetRange "10.0.0.0/16" `
  -Scope "authorized-pentest-2026-Q3" `
  -PentestPhase phase1-2-full `
  -UseMetasploit `
  -ActorRole "security-lead"

# 3. Check logs for findings
Get-Content "C:\Users\zeroi\Downloads\zeropoint-mcp\logs\autonomous_workflows.log" -Tail 200 | Where-Object { $_ -like "*finding*" }

# 4. Export audit trail for compliance
$audit = Get-Content "C:\Users\zeroi\Downloads\zeropoint-mcp\logs\audit_trail.json" | ConvertFrom-Json
$audit | Export-Csv "C:\work\audit-export-$(Get-Date -Format 'yyyyMMdd').csv" -NoTypeInformation
```

---

### **Device Recovery Technician**

Daily workflow:
```powershell
# 1. Verify cluster
.\operator.ps1 -Mode verify

# 2. Connect Android device via USB to ZERO-FLD

# 3. Run recovery triage
.\operator.ps1 -Mode recovery `
  -DeviceName "OnePlus-Model-X" `
  -Scope "recovery-ticket-$(Get-Date -Format 'yyyyMMddHHmm')" `
  -DeviceType android

# 4. Wait for completion and review extracted data
# (Check logs\autonomous_workflows.log for extracted paths)

# 5. Package evidence
$evidenceDir = "C:\Users\zeroi\Downloads\zeropoint-mcp\logs\evidence"
if (Test-Path $evidenceDir) {
    Compress-Archive -Path $evidenceDir -DestinationPath "C:\work\device-recovery-evidence.zip" -Force
}
```

---

### **SOC Analyst**

Daily workflow:
```powershell
# 1. Verify cluster
.\operator.ps1 -Mode verify

# 2. Process OSINT report
.\operator.ps1 -Mode analytics `
  -AnalysisType "summarize_osint" `
  -InputFile "C:\threats\daily_osint_$(Get-Date -Format 'yyyyMMdd').txt"

# 3. Extract IoCs from threat intel
.\operator.ps1 -Mode analytics `
  -AnalysisType "extract_iocs" `
  -InputFile "C:\threats\latest_threat_report.txt"

# 4. Triage alerts
.\operator.ps1 -Mode analytics `
  -AnalysisType "triage_alert" `
  -InputFile "C:\alerts\security_alert_001.json"

# 5. Consolidate findings
Get-ChildItem "C:\Users\zeroi\Downloads\zeropoint-mcp\logs\*.log" -Filter "*analytics*" | 
  ForEach-Object { Get-Content $_.FullName | Select-Object -Last 20 }
```

---

## 📞 Support & Escalation

**Issue:** Cluster down or unresponsive  
**Contact:** Infrastructure team  
**Expected response:** 1 hour

**Issue:** Role/permission denied  
**Contact:** Security manager  
**Expected response:** Same day

**Issue:** Tool not working as expected  
**Contact:** AI Operations team  
**Expected response:** 4 hours

**Incident Log:** `C:\Users\zeroi\Downloads\zeropoint-mcp\logs\incidents.log`

---

## 📖 Additional Resources

- **Full Project Scope:** [`PROJECT_SCOPE_HANDOFF.md`](PROJECT_SCOPE_HANDOFF.md)
- **Cluster Setup Guide:** [`CLUSTER_SETUP_GUIDE.md`](CLUSTER_SETUP_GUIDE.md)
- **System Overview:** [`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md)
- **GitHub Repository:** https://github.com/mrryandford-ui/zeropoint-mcp

---

## ✅ Checklist: First-Time Operator Setup

- [ ] Repo cloned to `C:\Users\zeroi\Downloads\zeropoint-mcp`
- [ ] Python venv exists (`.venv\Scripts\python.exe`)
- [ ] Ray cluster on ZERO-FLD is running
- [ ] Run `.\operator.ps1 -Mode verify` and see all checks pass
- [ ] Read the "Quick Start" section above
- [ ] Pick one workflow from the reference and copy/paste it
- [ ] Check logs in `logs\` directory to confirm task submission
- [ ] Review your role permissions with security admin
- [ ] Bookmark this runbook for daily reference

---

**Version:** Phase B - Unified UX (2026-08-12)  
**Last Verified:** Cluster healthy, all presets tested  
**Maintained By:** AI Operations Team
