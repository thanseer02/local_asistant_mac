"""Watchdog and health monitor for background threads and audio devices."""

import logging
import threading
import time
from typing import Callable, Dict, Optional

logger = logging.getLogger("MacAssistant.Watchdog")


class ServiceWatchdog:
    """Monitors worker threads and microphone devices.

    Restarts crashed threads and adapts to device disconnections (e.g. AirPods disconnect).
    """

    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self._services: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def register_service(
        self,
        name: str,
        is_alive_func: Callable[[], bool],
        restart_func: Callable[[], None]
    ) -> None:
        self._services[name] = {
            "is_alive": is_alive_func,
            "restart": restart_func,
            "restart_count": 0,
            "last_restart": 0.0
        }

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, name="MacAssistant-Watchdog", daemon=True
        )
        self._thread.start()
        logger.info("ServiceWatchdog started.")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _monitor_loop(self) -> None:
        while self._running:
            time.sleep(self.check_interval)
            for name, meta in list(self._services.items()):
                try:
                    alive = meta["is_alive"]()
                    if not alive:
                        now = time.time()
                        # Avoid rapid thrashing restart loop (min 3s between restarts)
                        if now - meta["last_restart"] > 3.0:
                            meta["restart_count"] += 1
                            meta["last_restart"] = now
                            logger.warning(
                                "Watchdog detected service '%s' died. Triggering restart (#%d)...",
                                name, meta["restart_count"]
                            )
                            meta["restart"]()
                except Exception as e:
                    logger.error("Watchdog error inspecting service '%s': %s", name, e)
