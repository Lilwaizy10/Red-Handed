"""FR3.2 / FR9.7: local JSON settings only, never camera or event data."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import tempfile

from red_handed.core.settings import MonitoringSettings, Sensitivity, ProtectionMode, ProtectionSettings
from red_handed.detection.privacy_zone import PrivacyZone
from red_handed.core.applications import ApplicationSettings, ProtectedApplication


def default_settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Local") / "Red-Handed" / "settings.json"


def backup_damaged_file(path: Path) -> Path:
    """Copy an unreadable file aside (never overwriting an earlier backup)."""
    target = path.with_name(path.name + ".bad")
    n = 1
    while target.exists():
        target = path.with_name(f"{path.name}.bad{n}")
        n += 1
    shutil.copy2(path, target)
    return target


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_settings_path()
        self.last_error: str | None = None
        # Only up to date after load() or save(); use load_protection() to be sure.
        self.protection_settings = ProtectionSettings()
        self.application_settings = ApplicationSettings()

    def load(self) -> MonitoringSettings:
        self.last_error = None
        self.protection_settings = ProtectionSettings()
        self.application_settings = ApplicationSettings()

        # Step 1: the file itself must be readable JSON in a format we know.
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(data, dict) or type(data.get("version")) is not int
                    or data["version"] != 1):
                raise ValueError("Unsupported settings format.")
        except FileNotFoundError:
            return MonitoringSettings()
        except (OSError, ValueError, RecursionError) as error:
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

        # Step 2b: application block (optional, so older v1 files still load).
        try:
            if "applications" in data:
                self.application_settings = self._parse_applications(data["applications"])
        except (ValueError, TypeError, KeyError) as error:
            self.application_settings = ApplicationSettings()
            problems.append(f"application settings ({error})")

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

    @staticmethod
    def _parse_applications(data):
        if not isinstance(data, dict) or not isinstance(data.get('protected_applications'), list):
            raise ValueError('Invalid application settings.')
        return ApplicationSettings(data['application_aware_enabled'],
            tuple(ProtectedApplication(**item) for item in data['protected_applications']))

    def save(self, settings: MonitoringSettings, *, protection: ProtectionSettings | None = None,
             applications: ApplicationSettings | None = None) -> None:
        """Validate and replace atomically; errors leave previous settings intact."""
        if not isinstance(settings, MonitoringSettings):
            raise ValueError("Invalid settings.")
        data = asdict(settings)
        data["version"] = 1

        # Read the existing file once. Valid optional blocks are carried over so
        # saving timing/zone settings never erases a saved hotkey or app list.
        # If anything in the old file is unreadable, a copy is kept before replacing.
        old, damaged = None, False
        if self.path.exists():
            try:
                old = json.loads(self.path.read_text(encoding="utf-8"))
                if (not isinstance(old, dict) or type(old.get("version")) is not int
                        or old["version"] != 1):
                    raise ValueError("Unsupported settings format.")
            except (ValueError, RecursionError):
                old, damaged = None, True
            except OSError:
                old = None
        if old is not None:
            if protection is None and "protection" in old:
                try:
                    protection = self._parse_protection(old["protection"])
                except (ValueError, TypeError, KeyError):
                    damaged = True
            if applications is None and "applications" in old:
                try:
                    applications = self._parse_applications(old["applications"])
                except (ValueError, TypeError, KeyError):
                    damaged = True

        if protection is not None:
            if not isinstance(protection, ProtectionSettings):
                raise ValueError('Invalid protection settings.')
            data['protection'] = asdict(protection)
        if applications is not None:
            if not isinstance(applications, ApplicationSettings):
                raise ValueError('Invalid application settings.')
            data['applications'] = asdict(applications)

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
            if damaged:
                backup_damaged_file(self.path)  # OSError here aborts the save; original stays
            os.replace(temporary, self.path)
            self.last_error = None
            if protection is not None:
                self.protection_settings = protection
            if applications is not None:
                self.application_settings = applications
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)