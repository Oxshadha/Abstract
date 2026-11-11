from app.adapters.scanner.clamav import ClamAVScanner
from app.adapters.scanner.fake import FakeScanner
from app.adapters.scanner.guardduty import GuardDutyScanner
from app.core.config import Settings
from app.ports.scanner import MalwareScanner


def build_scanner(settings: Settings) -> MalwareScanner | None:
    """None when scanning is off (MALWARE_SCAN=disabled-with-sanitization or unset in dev)."""
    mode = settings.resolved_malware_scan
    if mode == "fake":
        return FakeScanner()
    if mode == "clamav":
        return ClamAVScanner(settings.clamav_host, settings.clamav_port)
    if mode == "guardduty":
        return GuardDutyScanner(settings)
    return None
