"""
ZeroPoint Control Plane CLI — `zeropoint-control` command
Single unified CLI for the entire ZeroPoint stack.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import click
import yaml

DEFAULT_CONFIG = "/workspace/zeropoint/config/mcp_server_config.yaml"


def _cp(config: str):
    """Lazy-load control plane to avoid slow imports on --help."""
    from zeropoint.control_plane.control_plane import ZeroPointControlPlane
    cfg = yaml.safe_load(Path(config).read_text())
    cfg["_config_path"] = config
    return ZeroPointControlPlane(cfg)


def _json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, default=str))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


###############################################################################
# Root group
###############################################################################

@click.group()
@click.option("--config", "-c", default=DEFAULT_CONFIG, show_default=True,
              envvar="MCP_CONFIG", help="Path to mcp_server_config.yaml")
@click.pass_context
def main(ctx: click.Context, config: str):
    """ZeroPoint Unified Control Plane CLI."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


###############################################################################
# health
###############################################################################

@main.command()
@click.pass_context
def health(ctx: click.Context):
    """Check health of all ZeroPoint subsystems."""
    cp = _cp(ctx.obj["config"])

    async def _go():
        await cp.startup()
        result = await cp.health_check()
        await cp.shutdown()
        return result

    result = _run(_go())
    overall = "✅ HEALTHY" if result["overall_healthy"] else "⚠ DEGRADED"
    click.echo(f"\n{overall}  —  {result['healthy_count']}/{result['total_subsystems']} subsystems up\n")
    for name, status in result["subsystems"].items():
        icon = "✓" if status["healthy"] else "✗"
        click.echo(f"  {icon}  {name:<22} {status.get('details', {})}")
    click.echo()


###############################################################################
# server subgroup
###############################################################################

@main.group()
def server():
    """MCP server management."""


@server.command("start")
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
@click.pass_context
def server_start(ctx: click.Context, host: str | None, port: int | None):
    """Start the ZeroPoint MCP WebSocket server."""
    from zeropoint.server import main as _server_main
    _server_main(standalone_mode=False, args=[
        "--config", ctx.obj["config"],
        *(["--host", host] if host else []),
        *(["--port", str(port)] if port else []),
    ])


@server.command("tools")
@click.pass_context
def server_tools(ctx: click.Context):
    """List all registered MCP tools."""
    from zeropoint.registry import ToolRegistry
    reg = ToolRegistry(ctx.obj["config"])
    reg.load()
    tools = reg.list_tools()
    click.echo(f"\n{len(tools)} tools registered:\n")
    for t in tools:
        click.echo(f"  {t['name']:<35} {t['description'][:60]}")
    click.echo()


###############################################################################
# camnet subgroup
###############################################################################

@main.group()
def camnet():
    """CamNet device fleet management."""


@camnet.command("status")
@click.pass_context
def camnet_status(ctx: click.Context):
    """Show status of all CamNet devices."""
    from android.camnet_controller import CamNetController
    ctrl = CamNetController.from_config(ctx.obj["config"])

    async def _go():
        await ctrl.connect_all()
        return await ctrl.status()

    result = _run(_go())
    click.echo(f"\nCamNet [{result['network_id']}]  —  "
               f"{result['active_count']}/{len(result['devices'])} devices online\n")
    for d in result["devices"]:
        icon = "✓" if d["connected"] else "✗"
        batt = f"🔋{d['battery_pct']}%" if d["battery_pct"] >= 0 else "batt:?"
        click.echo(f"  {icon}  {d['device_id']:<10} {d['serial']:<22} {batt}  [{d['role']}]")
    click.echo()


@camnet.command("capture")
@click.option("--mode", type=click.Choice(["photo", "screencap"]), default="screencap")
@click.option("--devices", "-d", multiple=True, help="Specific device IDs (default: all)")
@click.pass_context
def camnet_capture(ctx: click.Context, mode: str, devices: tuple):
    """Trigger capture on CamNet devices."""
    from android.camnet_controller import CamNetController
    ctrl = CamNetController.from_config(ctx.obj["config"])

    async def _go():
        await ctrl.connect_all()
        return await ctrl.capture_all(
            device_ids=list(devices) or None,
            mode=mode,
            synchronized=True,
        )

    results = _run(_go())
    ok = sum(1 for r in results if r.success)
    click.echo(f"\nCapture [{mode}]: {ok}/{len(results)} succeeded\n")
    for r in results:
        icon = "✓" if r.success else "✗"
        path = r.local_path or "—"
        click.echo(f"  {icon}  {r.device_id:<12} {path}")
    click.echo()


@camnet.command("sync")
@click.option("--delete-after", is_flag=True, default=False,
              help="Delete files from device after sync")
@click.option("--dest", default=None, help="Override destination directory")
@click.pass_context
def camnet_sync(ctx: click.Context, delete_after: bool, dest: str | None):
    """Sync media from all CamNet devices to coordinator."""
    from android.camnet_controller import CamNetController
    ctrl = CamNetController.from_config(ctx.obj["config"])

    async def _go():
        await ctrl.connect_all()
        return await ctrl.sync_media(delete_after_sync=delete_after, destination=dest)

    result = _run(_go())
    kb = round(result["bytes_transferred"] / 1024, 1)
    click.echo(f"\nSync complete: {result['synced_files']} files, {kb} KB")
    if result["errors"]:
        click.echo(f"  ⚠ {len(result['errors'])} error(s):")
        for e in result["errors"]:
            click.echo(f"    — {e}")
    click.echo()


###############################################################################
# it subgroup
###############################################################################

@main.group()
def it():
    """IT support automation."""


@it.command("ticket")
@click.argument("title")
@click.argument("description")
@click.option("--severity", type=click.Choice(["low", "medium", "high", "critical"]),
              default="medium")
@click.pass_context
def it_ticket(ctx: click.Context, title: str, description: str, severity: str):
    """Create and auto-triage an IT support ticket."""
    from zeropoint.it_support import ITSupportAgent
    agent = ITSupportAgent()
    ticket = agent.create_ticket(title, description, severity)

    async def _go():
        diag = await agent.triage(ticket)
        remediation = await agent.auto_remediate(ticket, diag["issue_type"])
        return diag, remediation

    diag, rem = _run(_go())
    click.echo(f"\n[{ticket.ticket_id}] {ticket.title}")
    click.echo(f"  Severity   : {ticket.severity}")
    click.echo(f"  Classified : {diag['issue_type']}")
    click.echo(f"  Status     : {ticket.status}")
    click.echo(f"  Actions    : {'; '.join(rem['actions'][:3])}")
    click.echo()


@it.command("tickets")
@click.option("--status", default=None, help="Filter by status")
@click.pass_context
def it_tickets(ctx: click.Context, status: str | None):
    """List IT support tickets."""
    from zeropoint.it_support import ITSupportAgent
    agent = ITSupportAgent()
    tickets = agent.list_tickets(status=status)
    if not tickets:
        click.echo("No tickets found.")
        return
    for t in tickets:
        click.echo(f"  [{t['ticket_id']}] [{t['status']:<12}] {t['title']}")


###############################################################################
# osint subgroup
###############################################################################

@main.group()
def osint():
    """OSINT pipeline and investigations."""


@osint.command("scan")
@click.argument("target")
@click.option("--active", is_flag=True, default=False,
              help="Include active probing (port scan, subdomain brute-force)")
@click.pass_context
def osint_scan(ctx: click.Context, target: str, active: bool):
    """Run OSINT pipeline against a target domain or IP."""
    from zeropoint.osint import OSINTPipeline

    async def _go():
        async with OSINTPipeline() as pipeline:
            return await pipeline.run_all(target, active=active)

    result = _run(_go())
    click.echo(f"\nOSINT [{target}]  —  {result['module_count']} modules\n")
    for r in result["results"]:
        icon = "⚠" if r.get("error") else "✓"
        click.echo(f"  {icon}  {r.get('module', '?'):<25} "
                   f"{json.dumps(r.get('data', {}))[:80]}")
    click.echo()


@osint.command("case")
@click.argument("title")
@click.option("--priority", type=click.Choice(["low", "medium", "high", "critical"]),
              default="medium")
@click.pass_context
def osint_case(ctx: click.Context, title: str, priority: str):
    """Create a new investigation case."""
    from zeropoint.osint import InvestigationsAgent
    agent = InvestigationsAgent(cases_dir="/data/zeropoint/investigations")
    case = agent.create_case(title, priority=priority)
    click.echo(f"\nCase created: [{case.case_id}] {case.title}")
    click.echo(f"  Priority: {case.priority}  Status: {case.status}\n")


###############################################################################
# ai subgroup
###############################################################################

@main.group()
def ai():
    """Distributed AI orchestration."""


@ai.command("task")
@click.argument("task_type", type=click.Choice([
    "classify_it_issue", "summarize_osint", "extract_iocs",
    "triage_alert", "generate_report",
    "translate_text", "embed_text", "analyze_image",
]))
@click.argument("payload_json")
@click.pass_context
def ai_task(ctx: click.Context, task_type: str, payload_json: str):
    """Submit an AI task. PAYLOAD_JSON is a JSON string."""
    from zeropoint.control_plane.ai_orchestrator import AIOrchestrator
    orch = AIOrchestrator(
        ray_config={
            "head_node": os.environ.get("RAY_ADDRESS", "auto"),
            "namespace": "zeropoint",
        }
    )

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        click.echo(f"Invalid JSON payload: {exc}", err=True)
        sys.exit(1)

    async def _go():
        await orch.startup()
        return await orch.submit(task_type, payload)

    result = _run(_go())
    _json(result)


###############################################################################
# ray subgroup
###############################################################################

@main.group()
def ray_cmd():
    """Ray cluster management."""


ray_cmd.name = "ray"


@ray_cmd.command("status")
def ray_status():
    """Show Ray cluster status."""
    try:
        import ray as _ray
        if not _ray.is_initialized():
            _ray.init(address="auto", ignore_reinit_error=True)
        nodes = _ray.nodes()
        click.echo(f"\nRay cluster: {len(nodes)} node(s)\n")
        for n in nodes:
            alive = "✓ alive" if n.get("Alive") else "✗ dead"
            click.echo(
                f"  {alive}  {n.get('NodeManagerAddress','?'):<18} "
                f"CPU:{n.get('Resources',{}).get('CPU',0):.0f}  "
                f"RAM:{round(n.get('Resources',{}).get('memory',0)/1e9,1)}GB"
            )
        click.echo()
    except Exception as exc:
        click.echo(f"Ray not reachable: {exc}", err=True)


main.add_command(ray_cmd, name="ray")


if __name__ == "__main__":
    main()
