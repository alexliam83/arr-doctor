"""MCP server for Sonarr, Radarr and Prowlarr."""

import warnings

# fastmcp pulls in authlib, which emits deprecation warnings on import. They are
# harmless (and go to stderr) but clutter Claude Desktop's MCP log. authlib
# installs its own "always" filter when imported, so ours must go in after it.
try:
    from authlib.deprecate import AuthlibDeprecationWarning

    warnings.filterwarnings("ignore", category=AuthlibDeprecationWarning)
except ImportError:  # pragma: no cover - authlib is an indirect dependency
    pass

__version__ = "0.2.0"
