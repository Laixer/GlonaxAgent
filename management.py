import httpx
import logging
import traceback
from uuid import UUID

from models import GpsTelemetry, HostTelemetry

logger = logging.getLogger(__name__)


class ManagementService:
    def __init__(self, base_url: str, auth_token: str, instance_id: UUID):
        self._base_url = None
        self._auth_token = None

        headers = {
            "Authorization": "Basic " + auth_token,
            "User-Agent": "glonax-agent/1.0",
            "X-Instance-ID": str(instance_id),
        }

        self._client = httpx.AsyncClient(http2=True, base_url=base_url, headers=headers)

    async def notify(self, topic: str, message: str):
        try:
            response = await self._client.post(
                "/notify",
                json={"topic": topic, "message": message},
            )
            response.raise_for_status()

        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")

    async def remote_ip(self) -> str | None:
        try:
            response = await self._client.get("/ip")
            response.raise_for_status()

            response_data = response.json()
            return response_data["ip"]

        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")

    async def update_host_telemetry(self, telemetry: HostTelemetry):
        try:
            response = await self._client.post(
                "/telemetry_host", json=telemetry.as_dict()
            )
            response.raise_for_status()

        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")

    async def update_gps_telemetry(self, telemetry: GpsTelemetry):
        try:
            response = await self._client.post(
                "/telemetry_gps", json=telemetry.as_dict()
            )
            response.raise_for_status()

        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")
