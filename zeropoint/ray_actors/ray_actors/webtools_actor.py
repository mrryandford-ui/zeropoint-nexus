"""
ZeroPoint Ray Actor — WebtoolsActor
Distributes HTTP fetch, search, and scrape workloads across the Ray cluster.
One actor per worker node; the head node load-balances via ActorPool.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("zeropoint.ray_actors.webtools")

try:
    import ray

    @ray.remote(num_cpus=0.5, max_concurrency=20)
    class WebtoolsActor:
        """
        Stateful Ray actor that holds a persistent aiohttp session.
        Runs on a worker node — multiple requests share one session.

        Instantiate via ActorPool (see WebtoolsActorPool below).
        """

        def __init__(self, config: dict):
            import logging
            logging.basicConfig(level=logging.INFO)
            self._log = logging.getLogger("zeropoint.ray_actors.webtools")

            # Import here — inside the Ray worker process
            from zeropoint.tools.webtools import WebtoolsTool
            self._tool = WebtoolsTool(config=config)
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._tool.startup())
            self._log.info("WebtoolsActor ready.")

        def fetch(self, url: str, method: str = "GET",
                  headers: dict | None = None, body: str | None = None,
                  parse_as: str = "auto") -> dict:
            params = {"url": url, "method": method,
                      "headers": headers or {}, "parse_as": parse_as, "_op": "fetch"}
            if body:
                params["body"] = body
            return self._loop.run_until_complete(self._tool.safe_execute(params))

        def search(self, query: str, max_results: int = 10) -> dict:
            params = {"query": query, "max_results": max_results, "_op": "search"}
            return self._loop.run_until_complete(self._tool.safe_execute(params))

        def scrape(self, url: str, selectors: dict | None = None,
                   return_markdown: bool = True) -> dict:
            params = {"url": url, "selectors": selectors or {},
                      "return_markdown": return_markdown, "_op": "scrape"}
            return self._loop.run_until_complete(self._tool.safe_execute(params))

        def ping(self) -> bool:
            return True

        def shutdown(self) -> None:
            self._loop.run_until_complete(self._tool.shutdown())


    class WebtoolsActorPool:
        """
        Manages a pool of WebtoolsActor instances across cluster nodes.
        Provides async fetch/search/scrape with automatic load balancing.

        Usage:
            pool = WebtoolsActorPool.create(config, size=4)
            result = await pool.fetch("https://example.com")
        """

        def __init__(self, actors: list):
            from ray.util import ActorPool
            self._pool = ActorPool(actors)
            self._actors = actors

        @classmethod
        def create(cls, config: dict, size: int = 4) -> "WebtoolsActorPool":
            actors = [WebtoolsActor.remote(config) for _ in range(size)]
            ray.get([a.ping.remote() for a in actors])  # wait for all to init
            logger.info("WebtoolsActorPool: %d actors ready.", size)
            return cls(actors)

        async def fetch(self, url: str, **kwargs) -> dict:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: ray.get(self._pool.submit(lambda a, u: a.fetch.remote(u, **kwargs), url))
            )

        async def search(self, query: str, max_results: int = 10) -> dict:
            loop = asyncio.get_event_loop()
            actor = self._actors[hash(query) % len(self._actors)]
            return await loop.run_in_executor(
                None, lambda: ray.get(actor.search.remote(query, max_results))
            )

        async def scrape(self, url: str, selectors: dict | None = None) -> dict:
            loop = asyncio.get_event_loop()
            actor = self._actors[hash(url) % len(self._actors)]
            return await loop.run_in_executor(
                None, lambda: ray.get(actor.scrape.remote(url, selectors or {}))
            )

        async def batch_fetch(self, urls: list[str]) -> list[dict]:
            """Fetch multiple URLs in parallel across the pool."""
            loop = asyncio.get_event_loop()
            refs = [
                self._actors[i % len(self._actors)].fetch.remote(url)
                for i, url in enumerate(urls)
            ]
            return await loop.run_in_executor(None, lambda: ray.get(refs))

        def shutdown(self) -> None:
            for actor in self._actors:
                try:
                    ray.get(actor.shutdown.remote())
                    ray.kill(actor)
                except Exception:
                    pass
            logger.info("WebtoolsActorPool shutdown.")

except ImportError:
    # Ray not installed — provide stub so imports don't break
    class WebtoolsActor:  # type: ignore
        """Stub — Ray not installed."""

    class WebtoolsActorPool:  # type: ignore
        """Stub — Ray not installed."""
        @classmethod
        def create(cls, config: dict, size: int = 4):
            raise RuntimeError("Ray is not installed. Run: pip install 'ray[default]'")
