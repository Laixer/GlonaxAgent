import httpx
import logging
from uuid import UUID

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
            await self._client.post(
                "/notify",
                json={"topic": topic, "message": message},
            )
        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.error(f"Unknown error: {e}")

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
            logger.error(f"Unknown error: {e}")
