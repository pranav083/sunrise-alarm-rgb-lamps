"""Keep the Windows PC awake during a sunrise and wake it shortly before one."""
import ctypes
import logging
import subprocess
import sys
from datetime import datetime

log = logging.getLogger("sunlight.power")
ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
WAKE_TASK = "SunlightWake"


class Power:
    def keep_awake(self, on: bool) -> None:
        if sys.platform != "win32":
            log.info("keep_awake(%s) skipped (not Windows)", on)
            return
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)

    def schedule_wake(self, when: datetime) -> None:
        """(Re)register a one-shot task with WakeToRun that does nothing but wake the PC."""
        if sys.platform != "win32":
            log.info("schedule_wake(%s) skipped (not Windows)", when)
            return
        ps = (
            f"$t = New-ScheduledTaskTrigger -Once -At '{when:%Y-%m-%d %H:%M}';"
            "$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c exit';"
            "$s = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries;"
            f"Register-ScheduledTask -TaskName {WAKE_TASK} -Trigger $t -Action $a -Settings $s -Force | Out-Null"
        )
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30
            )
        except subprocess.TimeoutExpired:
            log.warning("schedule_wake timed out after 30s")
            return
        if r.returncode:
            log.warning("schedule_wake failed: %s", r.stderr.strip())
        else:
            log.info("wake timer set for %s", when)
