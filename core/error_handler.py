"""
Error Handler: Provides standardized error handling for the framework.
"""

import logging
import sys
import traceback
from typing import Dict, Any, Optional, Tuple, Type

from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

def handle_error(
    error: Exception,
    message: str,
    include_traceback: bool = True,
    log_error: bool = True
) -> Dict[str, Any]:
    """
    Handle an exception in a standardized way.
    
    Args:
        error: The exception to handle
        message: A descriptive message about what was happening when the error occurred
        include_traceback: Whether to include traceback in the result
        log_error: Whether to log the error
        
    Returns:
        Dictionary with error details
    """
    # Get exception details
    error_type = type(error).__name__
    error_message = str(error)
    
    # Format the error message
    full_message = f"{message}: {error_type}"
    if error_message:
        full_message += f" - {error_message}"
        
    # Get traceback if requested
    tb = None
    if include_traceback:
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        tb_str = "".join(tb)
    else:
        tb_str = None
        
    # Log the error if requested
    if log_error:
        if include_traceback:
            logger.error(full_message, exc_info=True)
        else:
            logger.error(full_message)
            
    # Create the error details dictionary
    error_details = {
        "message": full_message,
        "error_type": error_type,
        "error_message": error_message,
        "original_message": message
    }
    
    if tb_str:
        error_details["traceback"] = tb_str
        
    # Add additional error details for common exception types
    if isinstance(error, TimeoutError):
        error_details["error_category"] = "timeout"
    elif isinstance(error, ConnectionError):
        error_details["error_category"] = "connection"
    elif "NoSuchElement" in error_type:
        error_details["error_category"] = "element_not_found"
    elif "StaleElement" in error_type:
        error_details["error_category"] = "stale_element"
        
    return error_details

def handle_appium_error(
    error: Exception,
    message: str,
    retry_count: int = 0,
    max_retries: int = 3
) -> Tuple[Dict[str, Any], bool]:
    """
    Handle an Appium-specific exception.
    
    Args:
        error: The exception to handle
        message: A descriptive message about what was happening when the error occurred
        retry_count: Current retry count
        max_retries: Maximum number of retries
        
    Returns:
        Tuple of (error_details, should_retry)
    """
    error_details = handle_error(error, message)
    
    # Determine if the error is retriable
    retriable_errors = [
        "NoSuchElementException",
        "StaleElementReferenceException",
        "ElementNotVisibleException",
        "ElementNotInteractableException",
        "TimeoutException",
        "NoSuchWindowException",
        "WebDriverException",
        "ConnectionError",
        "TimeoutError"
    ]
    
    error_type = type(error).__name__
    should_retry = any(retriable in error_type for retriable in retriable_errors)
    
    # Check if we've exceeded max retries
    if retry_count >= max_retries:
        should_retry = False
        error_details["max_retries_exceeded"] = True
    else:
        error_details["retry_count"] = retry_count
        
    # Add retry information to the error details
    error_details["should_retry"] = should_retry
    
    return error_details, should_retry

def convert_error_for_reporting(error_details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert error details to a format suitable for reporting.
    
    Args:
        error_details: Error details from handle_error
        
    Returns:
        Simplified error details for reporting
    """
    report_error = {
        "message": error_details["message"],
        "type": error_details["error_type"]
    }
    
    # Include category if available
    if "error_category" in error_details:
        report_error["category"] = error_details["error_category"]
        
    # Include traceback if available and not too long
    if "traceback" in error_details:
        # Limit traceback length for reports
        tb = error_details["traceback"]
        if len(tb) > 1000:
            tb = tb[:500] + "...\n\n[traceback truncated]\n\n..." + tb[-500:]
        report_error["traceback"] = tb
        
    return report_error

class ErrorKind:
    """Constants for common error types."""
    ELEMENT_NOT_FOUND = "element_not_found"
    STALE_ELEMENT = "stale_element"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    APPIUM = "appium"
    LLM = "llm"
    UNKNOWN = "unknown"
    
def classify_error(error: Exception) -> str:
    """
    Classify an error into a known category.
    
    Args:
        error: The exception to classify
        
    Returns:
        Error category
    """
    error_type = type(error).__name__
    
    if "NoSuchElement" in error_type:
        return ErrorKind.ELEMENT_NOT_FOUND
    elif "StaleElement" in error_type:
        return ErrorKind.STALE_ELEMENT
    elif "Timeout" in error_type or isinstance(error, TimeoutError):
        return ErrorKind.TIMEOUT
    elif "Connection" in error_type or isinstance(error, ConnectionError):
        return ErrorKind.CONNECTION
    elif "WebDriver" in error_type or "Appium" in error_type or "Selenium" in error_type:
        return ErrorKind.APPIUM
    elif "OpenAI" in error_type or "LLM" in error_type or "API" in error_type:
        return ErrorKind.LLM
    else:
        return ErrorKind.UNKNOWN