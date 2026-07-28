import os


def get_runtime_env(key: str, default=None):
    value = os.getenv(key)
    if value not in (None, ""):
        return value

    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as registry_key:
                registry_value, _ = winreg.QueryValueEx(registry_key, key)
                if registry_value not in (None, ""):
                    return registry_value
        except FileNotFoundError:
            pass
        except OSError:
            pass

    return default
