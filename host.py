import time
import psutil
from models import Telemetry


class HostService:
    @staticmethod
    def uptime(self) -> int:
        return round(time.time() - psutil.boot_time())

    @staticmethod
    def get_telemetry():
        return Telemetry(
            memory_used=psutil.virtual_memory().percent,
            disk_used=psutil.disk_usage("/").percent,
            cpu_freq=psutil.cpu_freq().current,
            cpu_load=psutil.getloadavg(),
            uptime=HostService.uptime(),
        )

    # @staticmethod
    # def get_host_config():
    #     return HostConfig(
    #         hostname=os.uname().nodename,
    #         kernel=os.uname().release,
    #         memory_total=psutil.virtual_memory().total,
    #         cpu_count=psutil.cpu_count(),
    #         model=INSTANCE.model,
    #         version=INSTANCE.version_string,
    #         serial_number=INSTANCE.serial_number,
    #     )
