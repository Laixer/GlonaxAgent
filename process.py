import asyncio


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
            print(f"An error occurred: {str(e)}")
            return False

    async def reboot():
        print("Initiating system reboot...")

        reboot_process = await asyncio.create_subprocess_exec(
            "sudo",
            "systemctl",
            "reboot",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await reboot_process.communicate()

        if reboot_process.returncode == 0:
            print("Reboot command executed successfully.")
        else:
            print(f"Error during reboot: {stderr.decode().strip()}")

    async def systemctl(action: str, service_name: str | None = None):
        print(f"Initiating systemctl {action}...")

        systemctl_process = await asyncio.create_subprocess_exec(
            "sudo",
            "systemctl",
            action,
            service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await systemctl_process.communicate()

        if systemctl_process.returncode == 0:
            print(f"Systemctl {action} executed successfully.")
        else:
            print(f"Error during systemctl {action}: {stderr.decode().strip()}")
