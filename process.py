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
            "reboot",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await reboot_process.communicate()

        if reboot_process.returncode == 0:
            print("Reboot command executed successfully.")
        else:
            print(f"Error during reboot: {stderr.decode().strip()}")

    async def systemdctl(action: str, service_name: str):
        print(f"Initiating {action} on service: {service_name}...")

        process = await asyncio.create_subprocess_exec(
            "sudo",
            "systemctl",
            action,
            service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            print(f"Service {service_name} {action}ed successfully.")
            print(stdout.decode().strip())
        else:
            print(
                f"Error during {action} on service {service_name}: {stderr.decode().strip()}"
            )

