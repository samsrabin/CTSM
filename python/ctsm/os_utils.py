"""Various OS-related utility functions"""

import os
import subprocess
from ctsm.utils import abort


def run_cmd_output_on_error(cmd, errmsg, cwd=None):
    """Run the given command; suppress output but print it if there is an error

    If there is an error running the command, print the output from the command and abort
    with the given errmsg.

    Args:
    cmd: list of strings - command and its arguments
    errmsg: string - error message to print if the command returns an error code
    cwd: string or None - path from which the command should be run
    """
    try:
        _ = subprocess.check_output(cmd, stderr=subprocess.STDOUT, universal_newlines=True, cwd=cwd)
    except subprocess.CalledProcessError as error:
        print("ERROR while running:")
        print(" ".join(cmd))
        if cwd is not None:
            print("From {}".format(cwd))
        print("")
        print(error.output)
        print("")
        abort(errmsg)
    except:
        print("ERROR trying to run:")
        print(" ".join(cmd))
        if cwd is not None:
            print("From {}".format(cwd))
        raise


def make_link(src, dst):
    """Makes a link pointing to src named dst

    Does nothing if link is already set up correctly
    """
    if os.path.islink(dst) and os.readlink(dst) == src:
        # Link is already set up correctly: do nothing (os.symlink raises an exception if
        # you try to replace an existing file)
        pass
    else:
        os.symlink(src, dst)


def check_write_access(file_path: str) -> bool:
    """
    Check if user has write access to create/update a file.

    Args:
        file_path: Path to the file to check

    Returns:
        True if user has write access, False otherwise
    """
    # This function is only designed to work with files, not directories
    assert not os.path.isdir(file_path)

    # Get the directory where the file would be created
    directory = os.path.dirname(file_path) or "."

    # Check if directory exists and is writable
    if os.path.exists(directory):
        return os.access(directory, os.W_OK)

    # If directory doesn't exist, check parent directories
    parent = os.path.dirname(directory)
    while parent and not os.path.exists(parent):
        parent = os.path.dirname(parent)
    if not parent:
        raise FileNotFoundError("No parent directory found")

    return os.access(parent or ".", os.W_OK)
