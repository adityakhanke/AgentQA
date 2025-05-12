"""
Logger: Configures logging for the mobile testing framework.
"""

import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Configure colorized console output
try:
    import colorlog
    has_colorlog = True
except ImportError:
    has_colorlog = False

# Global logger cache
_loggers = {}

def setup_logger(
    log_level: str = "INFO",
    log_dir: str = "logs",
    log_filename: Optional[str] = None,
    console: bool = True,
    file: bool = True
) -> logging.Logger:
    """
    Configure the logging system for the framework.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        log_filename: Custom log filename (default: mobile_test_<timestamp>.log)
        console: Whether to log to console
        file: Whether to log to file
        
    Returns:
        The root logger
    """
    # Create log directory if it doesn't exist
    if file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # Generate a log filename with timestamp if not provided
        if not log_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"mobile_test_{timestamp}.log"
            
        log_file = log_path / log_filename
    
    # Get the numeric log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Format strings
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_format = '%(asctime)s - %(levelname)s - %(message)s'
    console_date_format = '%H:%M:%S'
    
    # Create console handler
    if console:
        if has_colorlog:
            # Color mapping
            colors = {
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
            
            # Create colored formatter
            console_formatter = colorlog.ColoredFormatter(
                f'%(log_color)s{console_format}',
                datefmt=console_date_format,
                log_colors=colors
            )
        else:
            console_formatter = logging.Formatter(
                console_format,
                datefmt=console_date_format
            )
            
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # Create file handler
    if file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)
    
    # Log initial message
    root_logger.info(f"Logging initialized at level {log_level}")
    if file:
        root_logger.info(f"Log file: {log_file}")
    
    # Store in cache
    _loggers['root'] = root_logger
    
    return root_logger

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with a specific name.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    # Check if logger already exists in cache
    if name in _loggers:
        return _loggers[name]
        
    # Check if root logger is configured
    if 'root' not in _loggers:
        # Configure default root logger if not already done
        setup_logger()
    
    # Create and cache the logger
    logger = logging.getLogger(name)
    _loggers[name] = logger
    
    return logger

def set_log_level(name: str, level: str) -> None:
    """
    Set the log level for a specific logger.
    
    Args:
        name: Logger name or 'root' for root logger
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")
    
    if name == 'root':
        logger = logging.getLogger()
    else:
        logger = logging.getLogger(name)
        
    logger.setLevel(numeric_level)
    
def create_test_logger(test_name: str, log_dir: str = "logs/tests") -> logging.Logger:
    """
    Create a logger specifically for a test.
    
    Args:
        test_name: Name of the test
        log_dir: Directory for test log files
        
    Returns:
        Logger configured for the test
    """
    # Sanitize test name for use in filenames
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in test_name)
    safe_name = safe_name.replace(" ", "_")
    
    # Create timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"test_{safe_name}_{timestamp}.log"
    
    # Set up a dedicated logger for this test
    return setup_logger(
        log_level="INFO",
        log_dir=log_dir,
        log_filename=log_filename,
        console=False,  # Don't duplicate console output
        file=True
    )