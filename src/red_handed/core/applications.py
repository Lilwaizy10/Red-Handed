"""FR8: executable identity and a camera/UI-independent protection gate."""

from dataclasses import dataclass
import ntpath


def executable_identity(path: str) -> str:
    if not isinstance(path, str) or not path or any(ord(c) < 32 for c in path):
        raise ValueError('Select an absolute Windows executable path.')
    path = path.replace('/', '\\')
    if path.startswith('\\\\?\\UNC\\'):
        path = '\\\\' + path[8:]
    elif path.startswith('\\\\?\\'):
        path = path[4:]
    drive, tail = ntpath.splitdrive(path)
    if not drive or not tail.startswith('\\') or not path.lower().endswith('.exe'):
        raise ValueError('Select an absolute Windows .exe file, not a shortcut.')
    return ntpath.normcase(ntpath.normpath(path))


@dataclass(frozen=True)
class ProtectedApplication:
    display_name: str
    executable_path: str

    def __post_init__(self):
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError('Application name is required.')
        object.__setattr__(self, 'executable_path', executable_identity(self.executable_path))

    @property
    def executable_name(self):
        return ntpath.basename(self.executable_path)


@dataclass(frozen=True)
class ApplicationSettings:
    application_aware_enabled: bool = False
    protected_applications: tuple[ProtectedApplication, ...] = ()

    def __post_init__(self):
        if type(self.application_aware_enabled) is not bool:
            raise ValueError('Application awareness must be enabled or disabled.')
        if not isinstance(self.protected_applications, tuple) or any(
                not isinstance(app, ProtectedApplication) for app in self.protected_applications):
            raise ValueError('Invalid protected-application list.')
        identities = [app.executable_path for app in self.protected_applications]
        if len(identities) != len(set(identities)):
            raise ValueError('This application is already protected.')


@dataclass(frozen=True)
class ActiveApplication:
    executable_path: str | None = None
    error: str | None = None
    protection_surface: bool = False

    @property
    def executable_name(self):
        return ntpath.basename(self.executable_path) if self.executable_path else 'Unavailable'


class ApplicationAwarePolicy:
    @staticmethod
    def allows(settings: ApplicationSettings, active: ActiveApplication) -> bool:
        # FR8.5 / FR8.6: this policy never changes privacy risk or manual requests.
        if not settings.application_aware_enabled:
            return True
        if active.error or not active.executable_path:
            return False
        try:
            identity = executable_identity(active.executable_path)
        except ValueError:
            return False
        return any(app.executable_path == identity for app in settings.protected_applications)