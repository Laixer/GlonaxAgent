import os
import time
import psutil
from glonax.message import Instance
from glonax_agent.models import HostTelemetry


class HostService:
    @staticmethod
    def uptime() -> int:
        return round(time.time() - psutil.boot_time())

    @staticmethod
    def get_telemetry(instance: Instance):
        return HostTelemetry(
            instance=str(instance.id),
            hostname=os.uname().nodename,
            kernel=os.uname().release,
            model=instance.model,
            version=instance.version_string,
            serial_number=instance.serial_number,
            memory_used=psutil.virtual_memory().percent,
            memory_total=psutil.virtual_memory().total,
            disk_used=psutil.disk_usage("/").percent,
            cpu_freq=psutil.cpu_freq().current,
            cpu_load=psutil.getloadavg(),
            cpu_count=psutil.cpu_count(),
            uptime=HostService.uptime(),
        )
