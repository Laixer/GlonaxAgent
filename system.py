import asyncio
import logging

logger = logging.getLogger(__name__)


class System:
    """A class that provides methods for system operations."""

    @staticmethod
    async def is_sudo() -> bool:
        """Check if the current user has sudo privileges.

        Returns:
            bool: True if the user has sudo privileges, False otherwise.
        """
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

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error checking sudo: {e}")
            return False

    @staticmethod
    async def reboot() -> bool:
        """Reboot the system.

        Returns:
            bool: True if the system reboot was successful, False otherwise.
        """
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

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error rebooting system: {e}")
            return False

    @staticmethod
    async def systemctl(action: str, service_name: str | None = None) -> bool:
        """Execute a systemctl command.

        Args:
            action (str): The systemctl action to perform.
            service_name (str | None, optional): The name of the service. Defaults to None.

        Returns:
            bool: True if the systemctl command was successful, False otherwise.
        """
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

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error during systemctl {action}: {e}")
            return False

    @staticmethod
    async def apt(action: str, package_name: str | None = None) -> bool:
        """Execute an apt command.

        Args:
            action (str): The apt action to perform.
            package_name (str | None, optional): The name of the package. Defaults to None.

        Returns:
            bool: True if the apt command was successful, False otherwise.
        """
        try:
            apt_process = await asyncio.create_subprocess_exec(
                "sudo",
                "apt",
                action,
                package_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await apt_process.communicate()
            if apt_process.returncode == 0:
                return True
            else:
                logger.error(f"Error during apt {action}: {stderr.decode().strip()}")
                return False

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error during apt {action}: {e}")
            return False

    @staticmethod
    async def ping(host: str) -> float | None:
        try:
            apt_process = await asyncio.create_subprocess_exec(
                "ping",
                "-c",
                "1",
                host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await apt_process.communicate()
            if apt_process.returncode == 0:
                time_str = stdout.decode().split("time=")[1].split(" ms")[0]
                return float(time_str)
            else:
                logger.error(f"Error during ping {stderr.decode().strip()}")
                return

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error during ping: {e}")
            return False
