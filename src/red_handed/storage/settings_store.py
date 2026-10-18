"""FR3.2 / FR9.7: local JSON settings only, never camera or event data."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

from red_handed.core.settings import MonitoringSettings, Sensitivity
from red_handed.detection.privacy_zone import PrivacyZone


def default_settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Local") / "Red-Handed" / "settings.json"


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_settings_path()
        self.last_error: str | None = None

    def load(self) -> MonitoringSettings:
        """Missing files use defaults; malformed files are preserved and reported."""
        self.last_error = None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("Unsupported settings format.")
            zone = data["privacy_zone"]
            return MonitoringSettings(
                privacy_zone=None if zone is None else PrivacyZone(**zone),
                sensitivity=Sensitivity(data["sensitivity"]),
                activation_delay=data["activation_delay"], recovery_delay=data["recovery_delay"],
            )
        except FileNotFoundError:
            return MonitoringSettings()
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.last_error = f"Settings could not be loaded; defaults are in use. {error}"
            return MonitoringSettings()

    def save(self, settings: MonitoringSettings) -> None:
        """Validate and replace atomically; errors leave previous settings intact."""
        if not isinstance(settings, MonitoringSettings):
            raise ValueError("Invalid settings.")
        data = asdict(settings)
        data["version"] = 1
        text = json.dumps(data, indent=2, allow_nan=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="settings-", suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                file.write(text)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            self.last_error = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
