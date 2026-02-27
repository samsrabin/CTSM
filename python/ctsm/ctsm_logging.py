"""Utilities to facilitate logging

A guide to logging in ctsm python scripts:

- At the top of each module, you should have:
  logger = logging.getLogger(__name__)

- Logging should be done via that logger, NOT via logging.[whatever]

- If you want to allow the user to control logging via command-line arguments, you should:

  (1) At the very start of a script / application, call setup_logging_pre_config(). (We
      need to initialize logging to avoid errors from logging calls made very early in the
      script.)

  (2) When setting up the argument parser, call add_logging_args(parser)

  (3) After parsing arguments, call process_logging_args(args)

- If you don't want to allow the user to control logging via command-line arguments, then
  simply:

  (1) At the very start of a script / application, call setup_logging() with the desired
      arguments

- In unit tests, to avoid messages about loggers not being set up, you should call
  setup_logging_for_tests (this is typically done via unit_testing.setup_for_tests)
"""

import inspect
import logging
import sys

from ctsm.utils import datetime_string

logger = logging.getLogger(__name__)

# In logfile lines, what should be used as spacing between the leading datetime string and the
# message text?
LOG_SPACING = " " * 4

# Modules can set this to True in order to just log their messages directly, without the stuff
# added in _compose_log_msg()
skip_compose = False  #  pylint: disable=invalid-name


def setup_logging_pre_config():
    """Setup logging for a script / application

    This function should be called at the very start of a script / application where you
    intend to allow the user to control logging preferences via command-line arguments.

    This sets initial options that may be changed later by process_logging_args.
    """
    setup_logging(level=logging.WARNING)


def setup_logging_for_tests(enable_critical=False):
    """Setup logging as appropriate for unit tests"""
    setup_logging(level=logging.CRITICAL)
    if not enable_critical:
        logging.disable(logging.CRITICAL)


def setup_logging(level=logging.WARNING):
    """Setup logging for a script / application

    This function should be called at the very start of a script / application where you
    do NOT intend to allow the user to control logging preferences via command-line
    arguments, so that all of the final logging options are set here.
    """
    logging.basicConfig(format="%(levelname)s: %(message)s", level=level)


def add_logging_args(parser):
    """Add common logging-related options to the argument parser"""

    logging_level = parser.add_mutually_exclusive_group()

    logging_level.add_argument(
        "-v", "--verbose", action="store_true", help="Output extra logging info"
    )
    logging_level.add_argument("--silent", action="store_true", help="Only output errors")

    logging_level.add_argument(
        "--debug",
        action="store_true",
        help="Output even more logging info for debugging",
    )


def logger_effectively_logs_to_file(logger_in: logging.Logger) -> bool:
    """Return True if the logger is writing to a file, False otherwise"""
    current = logger_in
    while current:
        if any(isinstance(h, logging.FileHandler) for h in current.handlers):
            return True
        if not current.propagate:
            break
        current = current.parent
    return False


def process_logging_args(args):
    """Configure logging based on the logging-related args added by add_logging_args"""
    root_logger = logging.getLogger()

    if args.debug:
        root_logger.setLevel(logging.DEBUG)
    elif args.verbose:
        root_logger.setLevel(logging.INFO)
    elif args.silent:
        root_logger.setLevel(logging.ERROR)
    else:
        root_logger.setLevel(logging.WARNING)


def output_to_file(file_path, message, log_to_logger=False):
    """
    helper function to write to log file.
    """
    with open(file_path, "a") as log_file:
        log_file.write(message)
    if log_to_logger:
        logger.info(message)


def _compose_log_msg(string, frame_record=2):
    """
    Prepend the log/error string with reference information
    """
    if skip_compose:
        return string

    # Get name of the function that called log() or error()
    caller_name = inspect.stack()[frame_record][3]

    return datetime_string() + LOG_SPACING + caller_name + LOG_SPACING + string


def debug(logger_in: logging.Logger, string: str):
    """
    Simultaneously print DEBUG messages to console and to log file
    """
    msg = _compose_log_msg(string)
    if logger_in:
        if logger_in.getEffectiveLevel() <= logging.DEBUG and logger_effectively_logs_to_file(
            logger_in
        ):
            print(msg)
        logger_in.debug(msg)
    else:
        print(msg)


def info(*args, **kwargs):
    """Alias for log()"""
    log(*args, **kwargs)


def log(logger_in: logging.Logger, string: str):
    """
    Simultaneously print INFO messages to console and to log file
    """
    msg = _compose_log_msg(string)
    if logger_in:
        if logger_in.getEffectiveLevel() <= logging.INFO and logger_effectively_logs_to_file(
            logger_in
        ):
            print(msg)
        logger_in.info(msg)
    else:
        print(msg)


def warn(logger_in: logging.Logger, string: str, **kwargs):
    """
    Simultaneously print WARNING messages to console and to log file
    """
    msg = _compose_log_msg(string)
    if logger_in:
        if logger_in.getEffectiveLevel() <= logging.WARNING and logger_effectively_logs_to_file(
            logger_in
        ):
            print(msg, **kwargs)
        logger_in.warning(msg)
    else:
        print(msg, **kwargs)


def error(logger_in: logging.Logger, string: str, *, error_type: Exception = RuntimeError):
    """
    Simultaneously print ERROR messages to console and to log file
    """
    msg = _compose_log_msg(string)
    if logger_in:
        if logger_in.getEffectiveLevel() <= logging.ERROR and logger_effectively_logs_to_file(
            logger_in
        ):
            print(msg, file=sys.stderr)
        logger_in.error(msg)
    else:
        print(msg, file=sys.stderr)
    try:
        raise error_type(string)
    except TypeError:
        # E.g., error_type=None
        pass
