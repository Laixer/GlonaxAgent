import asyncio
import logging

logger = logging.getLogger(__name__)


class System:
    async def is_sudo() -> bool:
        try:
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "-n",
                "true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await process.communicate()

            return process.returncode == 0

        except Exception as e:
            logger.error(f"Error checking sudo: {e}")
            return False

    async def reboot() -> bool:
        try:
            reboot_process = await asyncio.create_subprocess_exec(
                "sudo",
                "systemctl",
                "reboot",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await reboot_process.communicate()

            if reboot_process.returncode == 0:
                return True
            else:
                logger.error(f"Error rebooting system: {stderr.decode().strip()}")
                return False

        except Exception as e:
            logger.error(f"Error rebooting system: {e}")
            return False

    async def systemctl(action: str, service_name: str | None = None) -> bool:
        try:
            systemctl_process = await asyncio.create_subprocess_exec(
                "sudo",
                "systemctl",
                action,
                service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await systemctl_process.communicate()

            if systemctl_process.returncode == 0:
                return True
            else:
                logger.error(
                    f"Error during systemctl {action}: {stderr.decode().strip()}"
                )
                return False

        except Exception as e:
            logger.error(f"Error during systemctl {action}: {e}")
            return False
