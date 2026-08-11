# ZeroPoint MCP Cluster Configuration & Status

## 🏗️ Current Cluster Architecture

### Cluster Name: `ZeroPoint-MCP`

You have a **2-node distributed cluster** with specific roles:

```
┌─────────────────────────────────────────────────────────────┐
│                   ZEROPOINT-MCP CLUSTER                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ZERO-FLD (192.168.0.140)          ZERO-DEV (localhost)    │
│  ┌──────────────────────┐           ┌──────────────────┐   │
│  │ Role: HEAD/PRIMARY   │           │ Role: WORKER     │   │
│  │ Type: Backend/Master │           │ Type: Workstation│   │
│  │ MCP: 8765            │◄─────────►│ MCP: 8765        │   │
│  │ Ray Head: 6379       │ Cluster   │ Ray Worker: 6379 │   │
│  │ Status: UNREACHABLE  │ Network   │ Status: RUNNING  │   │
│  │ (from ZERO-DEV)      │           │ (THIS MACHINE)   │   │
│  └──────────────────────┘           └──────────────────┘   │
│         ▲                                    ▲              │
│         │ Ray Communication                 │ MCP Server   │
│         │ (port 6379)                       │ WebSocket    │
│         └────────────────────────────────────┘              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 📋 Node Details

### 1️⃣ ZERO-FLD (Head/Primary Node)
**IP Address:** `192.168.0.140`
- **Role:** `head` (Primary/Master)
- **Function:** Ray cluster head, orchestration, backend resources
- **Node ID:** `307a0cc30b3d43a3b5c38712bbdff03c`
- **MCP URL:** `http://192.168.0.140:8765`
- **Ray Address:** `192.168.0.140:6379`
- **Identity URL:** `http://192.168.0.140:8766`
- **Status:** ⚠️ **NOT REACHABLE** from ZERO-DEV (network issue or not running)

### 2️⃣ ZERO-DEV (Worker Node)  
**IP Address:** `localhost` / `100.125.25.3` (active network interface)
- **Role:** `worker` (Compute/Workstation)
- **Function:** Local workstation with tool registry and MCP access
- **Node ID:** `dd7103b7feef4c86bba116544b94c408`
- **MCP URL:** `http://localhost:8765`
- **Ray Address:** `192.168.0.140:6379` (connects to ZERO-FLD)
- **Identity URL:** `http://localhost:8766`
- **Status:** ✅ **RUNNING** (just started)
- **Tools Registered Locally:** 18

## 🔗 Current Connectivity Status

| Component | ZERO-DEV → ZERO-FLD | Status |
|-----------|-------------------|--------|
| Ray Head (6379) | ✗ TCP Timeout | ❌ BLOCKED |
| MCP Core (8765) | ✗ Not tested | ❌ UNKNOWN |
| Identity (8766) | ✗ Not tested | ❌ UNKNOWN |

**Issue:** Ray head node (ZERO-FLD) is configured but not reachable from ZERO-DEV.

## 🎯 Your Architecture is Correct!

**YES, you understood it right:**

- **ZERO-FLD** = Backend/Server node (provides cluster resources)
  - Runs Ray head node (orchestration)
  - Hosts primary MCP server
  - Manages cluster state
  - Provides shared resources to workers

- **ZERO-DEV** = Workstation/Client node (consumes resources)
  - Runs local MCP server with tools
  - Connects to Ray cluster
  - Uses ZERO-FLD resources for distributed tasks
  - Submits jobs to the cluster

## 🚀 How They Work Together (When Connected)

```
┌──────────────────────────────────────────────────────────┐
│ ZERO-DEV (Workstation)                                   │
│ ┌────────────────────────────────────────────────────┐   │
│ │ Local Tools (ADB, Android, etc.)  ← 18 tools      │   │
│ │ MCP Server: ws://localhost:8765/mcp               │   │
│ └────────────────────────────────────────────────────┘   │
│                      │                                    │
│  (1) User/Client requests task execution                 │
│                      │                                    │
│                      ▼                                    │
│ ┌────────────────────────────────────────────────────┐   │
│ │ Ray Worker Client                                  │   │
│ │ - Connects to Ray head at 192.168.0.140:6379      │   │
│ │ - Queues tasks for distribution                   │   │
│ └────────────────────────────────────────────────────┘   │
│                      │                                    │
│                      │ (2) Communicate via Ray           │
│                      │ (port 6379 tunnel)                │
│                      ▼                                    │
└──────────────────────────────────────────────────────────┘
                      ║
         ╔════════════╩════════════╗
         ║  Network Connection     ║
         ║  192.168.0.140:6379     ║
         ║  [CURRENTLY BROKEN]     ║
         ╚════════════╦════════════╝
                      ║
┌──────────────────────────────────────────────────────────┐
│ ZERO-FLD (Backend/Head Node)                             │
│ ┌────────────────────────────────────────────────────┐   │
│ │ Ray Head/Orchestrator                              │   │
│ │ - Receives task requests                           │   │
│ │ - Distributes work to available workers            │   │
│ │ - Manages cluster resources                        │   │
│ │ - Aggregates tool registries from all nodes        │   │
│ └────────────────────────────────────────────────────┘   │
│                                                          │
│ ┌────────────────────────────────────────────────────┐   │
│ │ MCP Identity Server (Central Registry)             │   │
│ │ - Cluster node discovery                           │   │
│ │ - Governance policies                              │   │
│ │ - Node health monitoring                           │   │
│ └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

## 📊 Resource Utilization Model

When fully operational:

### Local AIO Usage (ZERO-DEV)
```
User Request
    │
    ├─ Local Tools (ADB, Android)? → Execute Locally
    │
    └─ Distributed Task? → Send to Ray → ZERO-FLD executes
        (if available resources on ZERO-FLD)
```

### Inter-Node Communication
- **Ray RPC (port 6379):** Task execution, data sharing
- **MCP WebSocket (8765):** Tool availability, metadata
- **Identity Service (8766):** Node registration, health checks

## ⚠️ Current Issues

1. **Ray Connectivity Broken**
   - ZERO-DEV cannot reach ZERO-FLD on port 6379
   - Ray extension failed to import on ZERO-DEV
   - Possible causes:
     - ZERO-FLD not running Ray head
     - Firewall blocking port 6379
     - Network routing issue
     - MSVC runtime missing

2. **Not Functioning as Cluster**
   - ZERO-DEV is isolated, using only local tools
   - Cannot distribute tasks to ZERO-FLD
   - No shared resource access

## 🔧 Next Steps to Fix Connectivity

### Step 1: Verify ZERO-FLD is Running
On ZERO-FLD machine:
```powershell
.\dev_start.ps1 -RayHead
```

### Step 2: Check Network Connectivity
From ZERO-DEV:
```powershell
Test-NetConnection -ComputerName 192.168.0.140 -Port 6379
```

### Step 3: Verify Ray Head
On ZERO-FLD, check if Ray is running:
```bash
ray status
```

### Step 4: Configure Ray Workers
On ZERO-DEV, need to ensure Ray client connects:
```powershell
# Environment variable should point to head node
$env:RAY_ADDRESS = "192.168.0.140:6379"
```

## 📝 Configuration Files

| File | Purpose | Status |
|------|---------|--------|
| `cluster_registry.json` | Node topology, IPs, roles | ✓ Configured |
| `governance.json` | Policies, permissions, roles | ✓ Configured |
| `mcp_server_config.yaml` | Local MCP server config | ✓ Just fixed |
| `tool_registration.json` | Available tools manifest | ✓ Created |

## 🎯 Governance Policy

Current policies in `governance.json`:
- **Primary Head:** `ZERO-FLD`
- **Nodes:**
  - ZERO-DEV: worker
  - ZERO-FLD: head
- **Tool Usage Policies:**
  - Filesystem write: ❌ Disabled
  - ADB install APK: ✅ Enabled
- **Node Addition:** No approval required

## 📌 Summary

| Aspect | Status | Details |
|--------|--------|---------|
| **Cluster Config** | ✅ Set | 2-node cluster defined |
| **Local MCP** | ✅ Running | ZERO-DEV server active |
| **Ray Connectivity** | ❌ Broken | Cannot reach ZERO-FLD:6379 |
| **Governance** | ✅ Set | Policies configured |
| **Local Tools** | ✅ Ready | 18 tools available locally |
| **Cluster Operations** | ❌ Offline | No inter-node communication |

---

**Status:** Cluster is **configured but not operational**. Local machine (ZERO-DEV) works independently, but cannot communicate with backend (ZERO-FLD).

Next action: Fix Ray connectivity between nodes.
