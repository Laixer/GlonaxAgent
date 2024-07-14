import asyncio


async def proc_reboot():
    try:
        # Check if the user has sudo privileges
        process = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "true",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await process.communicate()

        if process.returncode == 0:
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
        else:
            print("Error: Insufficient privileges. This function requires sudo access.")

    except Exception as e:
        print(f"An error occurred: {str(e)}")


async def proc_service_restart(service_name):
    try:
        # Check if the user has sudo privileges
        process = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "true",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await process.communicate()

        if process.returncode == 0:
            print(f"Restarting service: {service_name}...")

            restart_process = await asyncio.create_subprocess_exec(
                "sudo",
                "systemctl",
                "restart",
                service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await restart_process.communicate()

            if restart_process.returncode == 0:
                print(f"Service {service_name} restarted successfully.")
            else:
                print(
                    f"Error restarting service {service_name}: {stderr.decode().strip()}"
                )
        else:
            print("Error: Insufficient privileges. This function requires sudo access.")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
