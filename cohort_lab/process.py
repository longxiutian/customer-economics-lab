"""Run native helpers without creating Windows console windows."""
import os
import subprocess

def run(*args, **kwargs):
    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
    return subprocess.run(*args, **kwargs)
