import logging
import sys

def setup_logging(level=logging.INFO):
    """Configure root logger with standard format and all levels."""
    # Validate log level if it's a string
    if isinstance(level, str):
        numeric_level = getattr(logging, level.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError(f"Invalid log level: {level}")
        level = numeric_level

    logging.basicConfig(
        level=level,
        format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout
    )

# Usage: import and call setup_logging() at the start of your main entry point.
