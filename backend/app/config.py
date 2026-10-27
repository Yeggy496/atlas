"""OptiDay settings, with compatibility for already deployed environments."""
import os


def env(name, default=None):
    """An explicit new value wins, including empty values; preserve old setups."""
    if name in os.environ:
        return os.environ[name]
    if name.startswith('OPTIDAY_'):
        legacy = 'ATLAS_' + name[len('OPTIDAY_'):]
        return os.getenv(legacy, default)
    return os.getenv(name, default)
