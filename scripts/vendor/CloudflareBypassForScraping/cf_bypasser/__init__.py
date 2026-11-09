__version__ = "3.0.0"
__author__ = "Sarper AVCI"

# GIL Research vendors the browser core only. Keeping package import free of
# the FastAPI server avoids pulling unused web-server dependencies into the
# research skill.
from .core.bypasser import CFBypasser

__all__ = ["CFBypasser"]
