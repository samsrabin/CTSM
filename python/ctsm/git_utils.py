"""General-purpose git utility functions"""

import logging
import subprocess
from pathlib import Path
from time import sleep

from ctsm.path_utils import path_to_ctsm_root

logger = logging.getLogger(__name__)


def get_ctsm_git_short_hash():
    """
    Returns Git short SHA for the CTSM repository.

    Args:

    Raises:

    Returns:
        sha (str) : git short hash for ctsm repository
    """
    sha = (
        subprocess.check_output(["git", "-C", path_to_ctsm_root(), "rev-parse", "--short", "HEAD"])
        .strip()
        .decode()
    )
    return sha


def get_ctsm_git_long_hash():
    """
    Returns Git long SHA for the CTSM repository.

    Args:

    Raises:

    Returns:
        sha (str) : git long hash for ctsm repository
    """
    sha = (
        subprocess.check_output(["git", "-C", path_to_ctsm_root(), "rev-parse", "HEAD"])
        .strip()
        .decode()
    )
    return sha


def get_ctsm_git_describe():
    """
    Function for giving the recent tag of the CTSM repository

    Args:

    Raises:

    Returns:
        label (str) : ouput of running 'git describe' for the CTSM repository
    """
    label = subprocess.check_output(["git", "-C", path_to_ctsm_root(), "describe"]).strip().decode()
    return label


def get_git_diff(
    repo_root: Path = Path(path_to_ctsm_root()),
    diff_args: list = None,
    capture_output: bool = True,
    check: bool = True,
    text: bool = True,
    **kwargs,
) -> None:
    """
    Get git diff for a repository. Default settings make it behave like other functions in this
    module (i.e., check result and capture stdout as text), but any keyword arg can be passed
    through to subprocess.run().
    """
    # Get the actual root of the repo

    cmd = [
        "git",
        "-c",
        "core.pager=cat",
        "-C",
        str(repo_root),
        "diff",
        "--color",
    ]
    if diff_args:
        if isinstance(diff_args, str):
            diff_args = [diff_args]
        cmd += diff_args

    result = subprocess.run(cmd, capture_output=capture_output, check=check, text=text, **kwargs)
    if not capture_output:
        sleep(0.1)
    return result


def get_git_toplevel(repo_root: Path = path_to_ctsm_root()):
    repo_root_orig = repo_root

    if isinstance(repo_root, str):
        repo_root = Path(repo_root)

    if not repo_root.exists():
        raise FileNotFoundError(f"repo_root does not exist: '{repo_root}'")

    while not (repo_root / ".git").is_dir():
        if repo_root == Path("/"):
            raise RuntimeError(f"'{repo_root_orig}' does not seem to be (in) a git repo")
        repo_root = repo_root.parent

    if isinstance(repo_root_orig, str):
        repo_root = str(repo_root)
    return repo_root
