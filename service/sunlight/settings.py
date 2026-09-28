"""Persisted alarm settings."""
import json
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class Settings:
    wake: str = "06:30"                       # HH:MM, local time; sunrise ends here
    days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # 0 = Monday
    length_min: int = 30
    hold_min: int = 30
    stay_on: bool = False
    floor: bool = True
    sunset: bool = True
    enabled: bool = True

    def validate(self) -> None:
        m = re.fullmatch(r"(\d{2}):(\d{2})", str(self.wake))
        if not m or int(m[1]) > 23 or int(m[2]) > 59:
            raise ValueError(f"wake must be HH:MM, got {self.wake!r}")
        if not isinstance(self.days, list) or any(not isinstance(d, int) or not 0 <= d <= 6 for d in self.days):
            raise ValueError("days must be a list of 0-6")
        if not 10 <= int(self.length_min) <= 60:
            raise ValueError("length_min must be 10-60")
        if int(self.hold_min) < 0:
            raise ValueError("hold_min must be >= 0")

    def to_dict(self) -> dict:
        return asdict(self)


def from_dict(d: dict) -> Settings:
    known = {f.name for f in fields(Settings)}
    s = Settings(**{k: v for k, v in d.items() if k in known})
    s.validate()
    return s


def load(path: Path) -> Settings:
    try:
        return from_dict(json.loads(Path(path).read_text()))
    except (OSError, ValueError, TypeError):
        return Settings()


def save(settings: Settings, path: Path) -> None:
    settings.validate()
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(settings.to_dict(), indent=2))
    tmp.replace(path)
