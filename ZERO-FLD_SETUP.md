# ZERO-FLD Setup Guide
## Complete instructions to prepare the backend/head node

---

## 🎯 WHAT YOU NEED TO DO

ZERO-FLD needs a **local copy** of the zeropoint-mcp repository. It cannot run from a network drive.

### Why Not Network Drive?
```
❌ Network Drive Issues:
  • Python virtual environment breaks
  • Ray cluster initialization fails
  • PowerShell execution policy blocks UNC paths
  • Severe performance degradation
  • Path resolution errors

✅ Local Drive Works:
  • Full filesystem access
  • Python venv operates normally
  • Ray initializes correctly
  • Performance is native speed
  • All scripts execute properly
```

---

## 📋 SETUP OPTIONS

### OPTION 1: Copy Locally (Easiest - Recommended)

**On ZERO-FLD Machine:**

1. **Create destination folder** (same location as ZERO-DEV for consistency):
```powershell
New-Item -ItemType Directory -Path "C:\Users\zeroi\Downloads" -Force
```

2. **Copy the entire zeropoint-mcp folder from ZERO-DEV**:
```powershell
# Option A: Via Network Share
#   Browse to \\<ZERO-DEV-IP>\Users\zeroi\Downloads
#   Copy zeropoint-mcp folder to your local C:\Users\zeroi\Downloads

# Option B: Via USB Drive
#   Copy to USB on ZERO-DEV
#   Plug into ZERO-FLD
#   Copy to C:\Users\zeroi\Downloads

# Option C: Via RDP File Transfer (if using Remote Desktop)
#   Use RDP file copy functionality
```

3. **Verify the copy**:
```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp
dir  # Should show all files

# Check for critical files:
Test-Path ".\dev_start.ps1"
Test-Path ".\.venv"
Test-Path ".\config\mcp_server_config.yaml"
```

4. **Test the setup**:
```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\dev_start.ps1 -RayHead
```

---

### OPTION 2: Git Clone (If Available)

**If your repo is on GitHub/GitLab:**

On ZERO-FLD:
```powershell
cd C:\Users\zeroi\Downloads
git clone <your-repo-url>
cd zeropoint-mcp

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

---

### OPTION 3: Sync Both Machines (Advanced)

Use `robocopy` to keep directories in sync:

```powershell
# From ZERO-DEV to ZERO-FLD
robocopy `
  "C:\Users\zeroi\Downloads\zeropoint-mcp" `
  "\\ZERO-FLD\C$\Users\zeroi\Downloads\zeropoint-mcp" `
  /E /PURGE /MIR
```

---

## 🔧 COMPLETE SETUP WALKTHROUGH

### Step 1: Prepare ZERO-FLD File System
```powershell
# On ZERO-FLD:
# Create the directory structure
New-Item -ItemType Directory -Path "C:\Users\zeroi\Downloads\zeropoint-mcp" -Force
```

### Step 2: Transfer the Repository

**Method A: Network Share (Fastest)**

On ZERO-DEV:
```powershell
# Enable file sharing (one-time setup)
New-NetFirewallRule -DisplayName "File Sharing" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 445

# Or use Windows Settings > Sharing options
```

On ZERO-FLD:
```powershell
# Map network drive
net use Z: \\<ZERO-DEV-IP>\Users\zeroi\Downloads

# Copy the folder
xcopy Z:\zeropoint-mcp C:\Users\zeroi\Downloads\zeropoint-mcp /E /I /Y

# Disconnect when done
net use Z: /delete
```

**Method B: USB Drive**

1. On ZERO-DEV: Copy `C:\Users\zeroi\Downloads\zeropoint-mcp` to USB
2. Move USB to ZERO-FLD
3. On ZERO-FLD: Copy from USB to `C:\Users\zeroi\Downloads\zeropoint-mcp`

**Method C: Physical Transfer (SSD)**

1. Attach external SSD to ZERO-DEV
2. Copy entire folder to SSD
3. Move SSD to ZERO-FLD
4. Copy from SSD to `C:\Users\zeroi\Downloads\zeropoint-mcp`

### Step 3: Verify the Copy

```powershell
# On ZERO-FLD:
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# Check structure
dir

# Check critical files exist
Test-Path ".\dev_start.ps1"                    # Should be True
Test-Path ".\manage_autostart.ps1"             # Should be True
Test-Path ".\config\mcp_server_config.yaml"    # Should be True
Test-Path ".\cluster_registry.json"            # Should be True
Test-Path ".\governance.json"                  # Should be True
Test-Path ".\.venv"                            # Should be True

# All should return True
```

### Step 4: Verify Python Virtual Environment

```powershell
# On ZERO-FLD:
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# Test Python venv
.\.venv\Scripts\python.exe --version
# Should show: Python 3.x.x

# Test Ray installation
.\.venv\Scripts\python.exe -c "import ray; print('Ray OK')"
# Should show: Ray OK

# Test zeropoint installation
.\.venv\Scripts\python.exe -c "import zeropoint; print('ZeroPoint OK')"
# Should show: ZeroPoint OK
```

### Step 5: Start the Head Node

```powershell
# On ZERO-FLD:
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# Start with Ray head
.\dev_start.ps1 -RayHead

# Expected output:
#   [OK] Loaded config\.env
#   [OK] Config loaded
#   [OK] MCP server started (Job ID: ...)
#   [OK] WebSocket : ws://localhost:8765/mcp
#   
#   ================================================
#   ZeroPoint is running!
#   ================================================
```

---

## 📊 VERIFICATION CHECKLIST

Run this on ZERO-FLD to verify everything is ready:

```powershell
Write-Host "ZERO-FLD Setup Verification"
Write-Host ""

$path = "C:\Users\zeroi\Downloads\zeropoint-mcp"

# Check directory exists
if (Test-Path $path) {
    Write-Host "✅ Repository directory exists"
} else {
    Write-Host "❌ Repository directory NOT FOUND"
    Write-Host "   Path: $path"
}

# Check critical files
$files = @(
    "dev_start.ps1",
    "manage_autostart.ps1",
    "config\mcp_server_config.yaml",
    "cluster_registry.json",
    "governance.json",
    ".venv\Scripts\python.exe"
)

foreach ($file in $files) {
    $fullPath = Join-Path $path $file
    if (Test-Path $fullPath) {
        Write-Host "✅ $file"
    } else {
        Write-Host "❌ $file NOT FOUND"
    }
}

# Check Python
$pythonPath = "$path\.venv\Scripts\python.exe"
if (Test-Path $pythonPath) {
    Write-Host "✅ Python venv found"
    $version = & $pythonPath --version
    Write-Host "   Version: $version"
} else {
    Write-Host "❌ Python venv NOT FOUND"
}

# Check Ray
Write-Host ""
Write-Host "Checking Ray installation..."
$rayTest = & $pythonPath -c "import ray; print('OK')" 2>&1
if ($rayTest -like "*OK*") {
    Write-Host "✅ Ray module installed"
} else {
    Write-Host "❌ Ray module NOT working"
}
```

---

## 🚨 TROUBLESHOOTING

### Issue: "Cannot find path"
**Cause:** Repo not fully copied
**Fix:** 
```powershell
# Verify source exists on ZERO-DEV
Test-Path "C:\Users\zeroi\Downloads\zeropoint-mcp"

# Copy manually if needed
Copy-Item "C:\Users\zeroi\Downloads\zeropoint-mcp" -Destination "\\ZERO-FLD\C$\Users\zeroi\Downloads\" -Recurse
```

### Issue: ".venv" not found
**Cause:** Virtual environment wasn't copied
**Fix:**
```powershell
# Go to ZERO-FLD, reinstall
cd C:\Users\zeroi\Downloads\zeropoint-mcp
pip install -r requirements.txt
pip install -e .
```

### Issue: "Python not found"
**Cause:** .venv wasn't installed
**Fix:**
```powershell
# Create new venv on ZERO-FLD
python -m venv .venv

# Activate and install
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

### Issue: "Ray initialization failed"
**Cause:** Dependencies missing
**Fix:**
```powershell
# Reinstall Ray specifically
.\.venv\Scripts\pip.exe install --upgrade ray
```

### Issue: "Access denied" on script execution
**Cause:** Execution policy on network drive
**Fix:**
```powershell
# Ensure local copy, then:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 📋 DIRECTORY STRUCTURE (After Setup)

ZERO-FLD should have this structure:

```
C:\Users\zeroi\Downloads\zeropoint-mcp\
├── .venv\                              (Python virtual environment)
│   ├── Scripts\
│   │   ├── python.exe                 (Python executable)
│   │   └── ...
│   └── ...
├── zeropoint\                          (Main package)
│   ├── server.py
│   ├── registry.py
│   └── ...
├── config\
│   ├── mcp_server_config.yaml         (Should be fixed version)
│   ├── .env                            (Auth tokens)
│   └── tool_registration.json
├── dev_start.ps1                       (Startup script)
├── manage_autostart.ps1
├── activate_cluster_head.ps1
├── verify_cluster_connection.ps1
├── cluster_registry.json               (Cluster topology)
├── governance.json                     (Policies)
├── requirements.txt
├── setup.py
└── ... (other files)
```

---

## ✅ NEXT STEPS AFTER SETUP

Once ZERO-FLD has the repo locally:

1. **On ZERO-FLD:**
```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\dev_start.ps1 -RayHead
```

2. **On ZERO-DEV:**
```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\verify_cluster_connection.ps1 -Verify
.\verify_cluster_connection.ps1 -Connect
```

3. **Result:** Full cluster active! 🎉

---

## 💡 RECOMMENDATIONS

### Disk Space
- Repo: ~500 MB
- venv: ~1-2 GB
- **Total: ~2.5 GB needed**

### Network Transfer Method (by speed)
1. **SSD Transfer** - Fastest (GB/s)
2. **Gigabit Network** - Fast (100+ MB/s)
3. **USB 3.0** - Medium (200+ MB/s)
4. **USB 2.0** - Slow (30 MB/s)

### Sync Strategy
- **Option 1:** Copy once, maintain separately
- **Option 2:** Keep synced with robocopy scheduled task
- **Option 3:** Git sync if using version control

---

**Status:** ZERO-FLD needs local copy of zeropoint-mcp  
**Action:** Choose transfer method above and copy repo  
**Next:** After copy, run `.\dev_start.ps1 -RayHead`
