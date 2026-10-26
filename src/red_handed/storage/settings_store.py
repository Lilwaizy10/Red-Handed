"""FR3.2 / FR9.7: local JSON settings only, never camera or event data."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

from red_handed.core.settings import MonitoringSettings, Sensitivity, ProtectionMode, ProtectionSettings
from red_handed.detection.privacy_zone import PrivacyZone


def default_settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Local") / "Red-Handed" / "settings.json"


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_settings_path()
        self.last_error: str | None = None
        # Only up to date after load() or save(); use load_protection() to be sure.
        self.protection_settings = ProtectionSettings()

    def load(self) -> MonitoringSettings:
        self.last_error = None
        self.protection_settings = ProtectionSettings()

        # Step 1: the file itself must be readable JSON in a format we know.
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("Unsupported settings format.")
        except FileNotFoundError:
            return MonitoringSettings()
        except (OSError, ValueError) as error:
            self.last_error = f"Settings could not be loaded; defaults are in use. {error}"
            return MonitoringSettings()

        problems = []  # names of the blocks that had to fall back to defaults

        # Step 2: protection block (optional, so older v1 files still load).
        try:
            if "protection" in data:
                self.protection_settings = self._parse_protection(data["protection"])
        except (ValueError, TypeError, KeyError) as error:
            self.protection_settings = ProtectionSettings()
            problems.append(f"protection settings ({error})")

        # Step 3: monitoring block (zone, sensitivity, delays).
        try:
            zone = data["privacy_zone"]
            monitoring = MonitoringSettings(
                privacy_zone=None if zone is None else PrivacyZone(**zone),
                sensitivity=Sensitivity(data["sensitivity"]),
                activation_delay=data["activation_delay"], recovery_delay=data["recovery_delay"],
            )
        except (ValueError, TypeError, KeyError) as error:
            monitoring = MonitoringSettings()
            problems.append(f"monitoring settings ({error})")

        if problems:
            self.last_error = ("Some settings could not be loaded; defaults are in use for: "
                               + "; ".join(problems) + ".")
        return monitoring

    def load_protection(self) -> ProtectionSettings:
        """Reload from disk and return the protection settings (for the view's get_settings)."""
        self.load()
        return self.protection_settings

    @staticmethod
    def _parse_protection(data) -> ProtectionSettings:
        return ProtectionSettings(ProtectionMode(data['mode']), data['hotkey'])

    def save(self, settings: MonitoringSettings, *, protection: ProtectionSettings | None = None) -> None:
        """Validate and replace atomically; errors leave previous settings intact."""
        if not isinstance(settings, MonitoringSettings):
            raise ValueError("Invalid settings.")
        data = asdict(settings)
        data["version"] = 1
        # Additive v1 extension: old Phase 3 files and APIs remain compatible.
        # Updating timing/zone settings must not erase a previously saved hotkey.
        if protection is None:
            try:
                old = json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(old, dict) and 'protection' in old:
                    protection = self._parse_protection(old['protection'])
            except (FileNotFoundError, ValueError, TypeError, KeyError):
                pass  # A deliberate Save may repair malformed settings.
        if protection is not None:
            if not isinstance(protection, ProtectionSettings):
                raise ValueError('Invalid protection settings.')
            data['protection'] = asdict(protection)
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
            if protection is not None:
                self.protection_settings = protection
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)