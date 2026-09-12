"""
ZeroPoint OSINT Pipeline
Passive and active intelligence gathering: DNS, WHOIS, IP geo,
subdomain enumeration, certificate transparency, and social footprint.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiohttp

logger = logging.getLogger("zeropoint.osint.pipeline")


@dataclass
class OSINTResult:
    target: str
    module: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "module": self.module,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
        }


class OSINTPipeline:
    """
    Modular OSINT pipeline. Each gather_* method returns an OSINTResult.
    run_all() executes all modules concurrently for a target.

    Passive only by default — active probing methods are flagged explicitly.
    """

    USER_AGENT = "ZeroPoint-OSINT/1.0 (research)"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": self.USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        return self

    async def __aexit__(self, *_):
        if self._session:
            await self._session.close()

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def run_all(self, target: str, active: bool = False) -> dict:
        """Run all passive (and optionally active) modules against target."""
        tasks = [
            self.gather_dns(target),
            self.gather_whois(target),
            self.gather_ip_geo(target),
            self.gather_cert_transparency(target),
            self.gather_http_headers(target),
        ]
        if active:
            tasks += [
                self.gather_subdomains(target),
                self.gather_port_scan(
                    target, ports=[21, 22, 23, 25, 53, 80, 443, 3306, 5432, 8080, 8443]
                ),
            ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for r in results:
            if isinstance(r, OSINTResult):
                output.append(r.to_dict())
            elif isinstance(r, Exception):
                output.append({"error": str(r)})

        return {
            "target": target,
            "active_mode": active,
            "module_count": len(output),
            "results": output,
            "run_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------
    # DNS
    # ------------------------------------------------------------------

    async def gather_dns(self, target: str) -> OSINTResult:
        module = "dns"
        try:
            loop = asyncio.get_event_loop()
            records: dict[str, Any] = {}

            for rtype in ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"):
                try:
                    import dns.resolver  # type: ignore

                    answers = await loop.run_in_executor(
                        None,
                        lambda r=rtype: dns.resolver.resolve(target, r, raise_on_no_answer=False),
                    )
                    records[rtype] = [str(a) for a in answers]
                except Exception:
                    records[rtype] = []

            return OSINTResult(target, module, {"records": records})
        except ImportError:
            # Fallback: socket-based A record only
            try:
                loop = asyncio.get_event_loop()
                addrs = await loop.run_in_executor(None, socket.gethostbyname_ex, target)
                return OSINTResult(
                    target, module, {"A": addrs[2], "note": "dnspython not installed"}
                )
            except Exception as exc:
                return OSINTResult(target, module, {}, error=str(exc))
        except Exception as exc:
            return OSINTResult(target, module, {}, error=str(exc))

    # ------------------------------------------------------------------
    # WHOIS
    # ------------------------------------------------------------------

    async def gather_whois(self, target: str) -> OSINTResult:
        module = "whois"
        try:
            import whois as pywhois  # type: ignore

            loop = asyncio.get_event_loop()
            w = await loop.run_in_executor(None, pywhois.whois, target)
            data = {k: str(v) for k, v in (w or {}).items() if v}
            return OSINTResult(target, module, data)
        except ImportError:
            return OSINTResult(target, module, {}, error="whois package not installed")
        except Exception as exc:
            return OSINTResult(target, module, {}, error=str(exc))

    # ------------------------------------------------------------------
    # IP Geolocation (ip-api.com — free, no key)
    # ------------------------------------------------------------------

    async def gather_ip_geo(self, target: str) -> OSINTResult:
        module = "ip_geo"
        try:
            # Resolve to IP first
            loop = asyncio.get_event_loop()
            ip = await loop.run_in_executor(None, socket.gethostbyname, target)

            # Skip private IPs
            if ipaddress.ip_address(ip).is_private:
                return OSINTResult(
                    target, module, {"ip": ip, "note": "Private IP — skipped geo lookup"}
                )

            assert self._session
            async with self._session.get(f"http://ip-api.com/json/{ip}?fields=66846719") as resp:
                data = await resp.json()
            data["resolved_ip"] = ip
            return OSINTResult(target, module, data)
        except Exception as exc:
            return OSINTResult(target, module, {}, error=str(exc))

    # ------------------------------------------------------------------
    # Certificate Transparency (crt.sh)
    # ------------------------------------------------------------------

    async def gather_cert_transparency(self, target: str) -> OSINTResult:
        module = "cert_transparency"
        try:
            assert self._session
            url = f"https://crt.sh/?q={target}&output=json"
            async with self._session.get(url) as resp:
                raw = await resp.json(content_type=None)

            domains: set[str] = set()
            issuers: set[str] = set()
            for entry in (raw or [])[:200]:
                name = entry.get("name_value", "")
                for d in name.splitlines():
                    d = d.strip().lstrip("*.")
                    if d:
                        domains.add(d)
                issuer = entry.get("issuer_ca_id", "")
                if issuer:
                    issuers.add(str(issuer))

            return OSINTResult(
                target,
                module,
                {
                    "subdomains_found": sorted(domains),
                    "cert_count": len(raw or []),
                    "unique_subdomains": len(domains),
                },
            )
        except Exception as exc:
            return OSINTResult(target, module, {}, error=str(exc))

    # ------------------------------------------------------------------
    # HTTP Headers (passive fingerprinting)
    # ------------------------------------------------------------------

    async def gather_http_headers(self, target: str) -> OSINTResult:
        module = "http_headers"
        results = {}
        for scheme in ("https", "http"):
            url = f"{scheme}://{target}"
            try:
                assert self._session
                async with self._session.head(url, allow_redirects=True) as resp:
                    results[scheme] = {
                        "status": resp.status,
                        "final_url": str(resp.url),
                        "server": resp.headers.get("Server", ""),
                        "x_powered_by": resp.headers.get("X-Powered-By", ""),
                        "x_frame_options": resp.headers.get("X-Frame-Options", ""),
                        "content_security_policy": resp.headers.get("Content-Security-Policy", "")[
                            :200
                        ],
                        "strict_transport_security": resp.headers.get(
                            "Strict-Transport-Security", ""
                        ),
                        "set_cookie": "present" if "Set-Cookie" in resp.headers else "absent",
                    }
                break
            except Exception as exc:
                results[scheme] = {"error": str(exc)}

        return OSINTResult(target, module, results)

    # ------------------------------------------------------------------
    # Subdomain enumeration (active — wordlist based)
    # ------------------------------------------------------------------

    async def gather_subdomains(
        self, target: str, wordlist: list[str] | None = None
    ) -> OSINTResult:
        module = "subdomains_active"
        common = wordlist or [
            "www",
            "mail",
            "ftp",
            "smtp",
            "api",
            "dev",
            "staging",
            "test",
            "admin",
            "vpn",
            "portal",
            "app",
            "cdn",
            "static",
            "img",
            "remote",
            "citrix",
            "webmail",
            "secure",
            "shop",
            "blog",
        ]
        found = []
        loop = asyncio.get_event_loop()

        async def _check(sub: str):
            fqdn = f"{sub}.{target}"
            try:
                await loop.run_in_executor(None, socket.gethostbyname, fqdn)
                found.append(fqdn)
            except socket.gaierror:
                pass

        await asyncio.gather(*[_check(s) for s in common])
        return OSINTResult(target, module, {"found": sorted(found), "tested": len(common)})

    # ------------------------------------------------------------------
    # Port scan (active)
    # ------------------------------------------------------------------

    async def gather_port_scan(self, target: str, ports: list[int] | None = None) -> OSINTResult:
        module = "port_scan_active"
        ports = ports or [22, 80, 443, 8080, 8443]
        loop = asyncio.get_event_loop()
        open_ports = []

        async def _probe(port: int):
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=2)
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                open_ports.append(port)
            except Exception:
                pass

        await asyncio.gather(*[_probe(p) for p in ports])
        return OSINTResult(
            target,
            module,
            {
                "open_ports": sorted(open_ports),
                "scanned": len(ports),
                "note": "TCP connect scan only",
            },
        )
