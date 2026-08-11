"""
ZeroPoint Ray Actor — CamNetActor
Distributes CamNet capture and sync workloads across the Ray cluster.
Each actor is pinned to a specific device-host node.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("zeropoint.ray_actors.camnet")

try:
    import ray

    @ray.remote(num_cpus=0.25, max_concurrency=8)
    class CamNetActor:
        """
        Stateful Ray actor wrapping one or more CamNet devices.
        Pinned to a specific node via placement groups.

        Each actor manages its own CamNetController instance
        so device connections survive across multiple task calls.
        """

        def __init__(self, config_path: str, device_ids: list[str] | None = None):
            import asyncio, logging
            logging.basicConfig(level=logging.INFO)
            self._log = logging.getLogger("zeropoint.ray_actors.camnet")
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            from android.camnet_controller import CamNetController
            self._ctrl = CamNetController.from_config(config_path)
            self._device_ids = device_ids

            # Connect devices at startup
            results = self._loop.run_until_complete(
                self._ctrl.connect_all(device_ids)
            )
            ok = sum(1 for v in results.values() if v)
            self._log.info(
                "CamNetActor: %d/%d devices connected.", ok, len(results)
            )

        def ping(self) -> bool:
            return True

        # ------------------------------------------------------------------
        # Status
        # ------------------------------------------------------------------

        def status(self, device_ids: list[str] | None = None) -> dict:
            return self._loop.run_until_complete(
                self._ctrl.status(device_ids or self._device_ids)
            )

        # ------------------------------------------------------------------
        # Capture
        # ------------------------------------------------------------------

        def capture(
            self,
            mode: str = "photo",
            device_ids: list[str] | None = None,
            synchronized: bool = True,
        ) -> list[dict]:
            results = self._loop.run_until_complete(
                self._ctrl.capture_all(
                    device_ids=device_ids or self._device_ids,
                    mode=mode,
                    synchronized=synchronized,
                )
            )
            return [r.to_dict() for r in results]

        def screencap(self, device_ids: list[str] | None = None) -> list[dict]:
            return self.capture(mode="screencap", device_ids=device_ids)

        # ------------------------------------------------------------------
        # Sync
        # ------------------------------------------------------------------

        def sync_media(
            self,
            device_ids: list[str] | None = None,
            media_type: str = "all",
            delete_after_sync: bool = False,
            destination: str | None = None,
        ) -> dict:
            return self._loop.run_until_complete(
                self._ctrl.sync_media(
                    device_ids=device_ids or self._device_ids,
                    media_type=media_type,
                    delete_after_sync=delete_after_sync,
                    destination=destination,
                )
            )

        # ------------------------------------------------------------------
        # UI automation
        # ------------------------------------------------------------------

        def tap(self, device_id: str, x: float, y: float) -> dict:
            return self._loop.run_until_complete(
                self._ctrl.tap(device_id=device_id, x=x, y=y)
            )

        def swipe(
            self,
            device_id: str,
            start_x: float, start_y: float,
            end_x: float, end_y: float,
            duration_ms: int = 300,
        ) -> dict:
            return self._loop.run_until_complete(
                self._ctrl.swipe(device_id, start_x, start_y, end_x, end_y, duration_ms)
            )

        def input_text(self, device_id: str, text: str, clear_first: bool = True) -> dict:
            return self._loop.run_until_complete(
                self._ctrl.input_text(device_id, text, clear_first)
            )

        def shutdown(self) -> None:
            self._loop.run_until_complete(self._ctrl.disconnect_all())
            self._log.info("CamNetActor shutdown.")


    class CamNetActorPool:
        """
        Manages CamNetActor instances — one per device group / cluster node.
        Supports synchronized multi-actor capture for true parallel fleet control.

        Usage:
            pool = CamNetActorPool.create(config_path, groups={"node-0": ["cam-0","cam-1"],
                                                                "node-1": ["cam-2","cam-3"]})
            results = await pool.capture_all(mode="photo")
        """

        def __init__(self, actors: dict[str, Any]):
            # actors: {group_name -> CamNetActor remote handle}
            self._actors = actors

        @classmethod
        def create(
            cls,
            config_path: str,
            groups: dict[str, list[str]] | None = None,
        ) -> "CamNetActorPool":
            """
            Create one actor per device group.
            Default: two groups splitting cam-0/1 and cam-2/3 across nodes.
            """
            if groups is None:
                groups = {
                    "group-0": ["cam-0", "cam-1"],
                    "group-1": ["cam-2", "cam-3"],
                }

            actors = {}
            for group_name, device_ids in groups.items():
                actors[group_name] = CamNetActor.remote(config_path, device_ids)

            # Wait for all actors to initialize
            ray.get([a.ping.remote() for a in actors.values()])
            logger.info(
                "CamNetActorPool: %d groups ready — %s",
                len(actors), list(actors.keys()),
            )
            return cls(actors)

        async def _run(self, ref):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, ray.get, ref)

        async def status_all(self) -> dict:
            loop = asyncio.get_event_loop()
            refs = {g: a.status.remote() for g, a in self._actors.items()}
            results = {}
            for group, ref in refs.items():
                results[group] = await loop.run_in_executor(None, ray.get, ref)
            return results

        async def capture_all(
            self,
            mode: str = "photo",
            synchronized: bool = True,
        ) -> list[dict]:
            """
            Trigger simultaneous capture across ALL actor groups.
            Returns flat list of CaptureResult dicts from all devices.
            """
            loop = asyncio.get_event_loop()
            # Fire all actors at exactly the same time
            refs = [a.capture.remote(mode, None, synchronized)
                    for a in self._actors.values()]
            nested = await loop.run_in_executor(None, ray.get, refs)
            # Flatten
            return [item for sublist in nested for item in sublist]

        async def sync_all(
            self,
            media_type: str = "all",
            delete_after_sync: bool = False,
        ) -> list[dict]:
            loop = asyncio.get_event_loop()
            refs = [
                a.sync_media.remote(None, media_type, delete_after_sync)
                for a in self._actors.values()
            ]
            return await loop.run_in_executor(None, ray.get, refs)

        async def screencap_all(self) -> list[dict]:
            loop = asyncio.get_event_loop()
            refs = [a.screencap.remote() for a in self._actors.values()]
            nested = await loop.run_in_executor(None, ray.get, refs)
            return [item for sublist in nested for item in sublist]

        def shutdown(self) -> None:
            for name, actor in self._actors.items():
                try:
                    ray.get(actor.shutdown.remote())
                    ray.kill(actor)
                    logger.info("Killed CamNetActor: %s", name)
                except Exception:
                    pass

except ImportError:
    class CamNetActor:  # type: ignore
        """Stub — Ray not installed."""

    class CamNetActorPool:  # type: ignore
        """Stub — Ray not installed."""
        @classmethod
        def create(cls, *args, **kwargs):
            raise RuntimeError("Ray is not installed. Run: pip install 'ray[default]'")
