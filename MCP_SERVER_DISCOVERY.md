# 🔍 MCP SERVER DISCOVERY & SYNC PROCEDURE

## CRITICAL FINDING

You're seeing 16 MCP servers on ZERO-FLD (Lenovo) in VS Code, but ZERO-DEV (HP Envy) is missing them. This means ZERO-FLD has been configured with additional MCP servers that we need to sync.

---

## STEP 1: Export ZERO-FLD's MCP Server Configuration

**Go to ZERO-FLD (Lenovo IdeaPad 5) and:**

1. Open VS Code
2. Press `Ctrl + Shift + D` (or go to Settings icon → Settings)
3. Search for: `github.copilot.chat.agent.mcpServers`
4. You should see a list of 16 MCP servers
5. **Take a screenshot** or **copy the entire configuration** and paste it in a file

---

## STEP 2: Find the Actual Settings File

**On ZERO-FLD, find VS Code settings:**

In File Explorer:
```
C:\Users\zeroi\AppData\Roaming\Code\User\settings.json
```

Or in Terminal:
```powershell
# Show the full settings file
cat $env:APPDATA\Code\User\settings.json
```

**Copy the entire contents and save it somewhere we can access.**

---

## STEP 3: Check for External MCP Server Definitions

ZERO-FLD might have MCP server definitions in:

1. **Claude Desktop settings:**
   ```
   C:\Users\zeroi\AppData\Roaming\Claude\claude_desktop_config.json
   ```

2. **Project-level configuration:**
   ```
   Z:\Downloads\zeropoint-mcp\.vscode\extensions\mcp-config.json
   Z:\Downloads\zeropoint-mcp\config\mcp-servers.json
   ```

3. **Any additional .json files** in `.vscode` folder

---

## STEP 4: What We Need to Find

The 16 MCP servers likely include:

- ✓ zeropoint-mcp (the local cluster)
- ✓ Additional security/analysis tools
- ✓ External tool integrations
- ✓ Specialized analysis modules
- ? Claude servers
- ? Other AI integrations

---

## IMMEDIATE ACTION NEEDED

Since you're at ZERO-DEV right now:

1. **Open the guide at:** `C:\Users\zeroi\Downloads\zeropoint-mcp\MCP_SERVER_DISCOVERY.md` (this file)

2. **Go to ZERO-FLD and:**
   - Open VS Code Settings
   - Search for `mcpServers`
   - Screenshot or export what you find
   - Share the configuration

3. **Return to ZERO-DEV**
   - I'll sync those configurations
   - Both machines will have all 16 MCP servers
   - Full parity achieved

---

## Why This Matters

- **ZERO-FLD has 16 MCP servers** = Sophisticated tooling for backend
- **ZERO-DEV has <5 MCP servers** = Missing capabilities
- **We need parity** = Both machines should have same tools
- **Cluster advantage** = Frontend can call backend MCP servers too

---

## Quick Diagnosis

Can you tell me:

1. **In VS Code on ZERO-FLD**, what are the names of the 16 MCP servers? (List the first 5-10 names)
2. **Are they configured in:**
   - VS Code Settings (global)?
   - Claude Desktop config?
   - Project .vscode folder?
   - Somewhere else?

3. **Are they all `http://localhost:####` endpoints or some external?**

---

**This is important to get right - we need ZERO-DEV (frontend) to have access to all the same capabilities as ZERO-FLD (backend) so the cluster can work efficiently.**
