"""Root conftest.py: add the repository parent directory to sys.path so that the
integration is importable as the ``ssh_command`` package."""

import sys
import os

# The repository directory is named "ssh_command", so adding its parent lets
# Python resolve ``import ssh_command`` to the integration source files.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
