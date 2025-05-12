"""
Wait: Provides utilities for explicit waiting and synchronization.
"""

import asyncio
import logging
import time
from typing import Callable, Any, Optional, Union, Tuple

from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

async def wait_until(
    condition: Callable[[], Union[bool, Any]],
    timeout: float = 30.0,
    interval: float = 0.5,
    message: str = "Condition not met within timeout period",
    check_interval_growth_factor: float = 1.0,
    initial_delay: float = 0.0,
    ignore_exceptions: bool = False
) -> Tuple[bool, Any]:
    """
    Wait until a condition is met or timeout expires.
    
    Args:
        condition: Function that returns True when condition is met, or the value to return
        timeout: Maximum time to wait in seconds
        interval: Time between condition checks in seconds
        message: Error message if timeout occurs
        check_interval_growth_factor: Factor to increase check interval (1.0 = constant)
        initial_delay: Time to wait before first condition check
        ignore_exceptions: Whether to ignore exceptions in condition function
        
    Returns:
        Tuple of (success, result) where result is the return value of the condition function
    """
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
        
    start_time = time.time()
    check_interval = interval
    last_exception = None
    
    # Keep checking until timeout
    while time.time() - start_time < timeout:
        try:
            result = condition()
            
            # If condition returns a truthy value, we're done
            if result:
                return True, result
                
        except Exception as e:
            if not ignore_exceptions:
                logger.warning(f"Exception during wait condition: {str(e)}")
                raise
            last_exception = e
            
        # Wait before next check
        await asyncio.sleep(check_interval)
        
        # Increase check interval if growth factor is greater than 1
        if check_interval_growth_factor > 1.0:
            check_interval = min(check_interval * check_interval_growth_factor, timeout / 10)
            
    # Timeout occurred
    if last_exception and ignore_exceptions:
        logger.warning(f"Wait timed out with last exception: {str(last_exception)}")
        
    logger.warning(f"Wait timed out: {message}")
    return False, None

async def wait_for_true(
    condition: Callable[[], bool],
    timeout: float = 30.0,
    interval: float = 0.5,
    message: str = "Condition not met within timeout period",
    ignore_exceptions: bool = False
) -> bool:
    """
    Wait until a condition returns True or timeout expires.
    
    Args:
        condition: Function that returns True when condition is met
        timeout: Maximum time to wait in seconds
        interval: Time between condition checks in seconds
        message: Error message if timeout occurs
        ignore_exceptions: Whether to ignore exceptions in condition function
        
    Returns:
        True if condition was met, False if timeout occurred
    """
    success, _ = await wait_until(
        condition=condition,
        timeout=timeout,
        interval=interval,
        message=message,
        ignore_exceptions=ignore_exceptions
    )
    return success

async def wait_for_value(
    supplier: Callable[[], Any],
    timeout: float = 30.0,
    interval: float = 0.5,
    message: str = "Value not available within timeout period",
    ignore_exceptions: bool = False
) -> Tuple[bool, Any]:
    """
    Wait until a function returns a non-None, non-False value or timeout expires.
    
    Args:
        supplier: Function that returns the value to wait for
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds
        message: Error message if timeout occurs
        ignore_exceptions: Whether to ignore exceptions in supplier function
        
    Returns:
        Tuple of (success, value) where value is the return value of the supplier function
    """
    return await wait_until(
        condition=supplier,
        timeout=timeout,
        interval=interval,
        message=message,
        ignore_exceptions=ignore_exceptions
    )

async def wait_for_element(
    element_finder: Callable[[], Any],
    timeout: float = 30.0,
    interval: float = 0.5,
    message: Optional[str] = None,
    visible: bool = False
) -> Tuple[bool, Any]:
    """
    Wait for an element to be present or visible.
    
    Args:
        element_finder: Function that returns the element when found
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds
        message: Error message if timeout occurs
        visible: Whether to wait for element to be visible (not just present)
        
    Returns:
        Tuple of (success, element) where element is the found element
    """
    if message is None:
        message = f"Element not {'visible' if visible else 'present'} within timeout period"
        
    def check_element():
        try:
            element = element_finder()
            if element:
                if visible:
                    if hasattr(element, "is_displayed") and callable(element.is_displayed):
                        return element if element.is_displayed() else None
                    return element
                return element
            return None
        except Exception:
            return None
            
    return await wait_until(
        condition=check_element,
        timeout=timeout,
        interval=interval,
        message=message,
        ignore_exceptions=True
    )

async def wait_for_not_element(
    element_finder: Callable[[], Any],
    timeout: float = 30.0,
    interval: float = 0.5,
    message: Optional[str] = None
) -> bool:
    """
    Wait for an element to not be present.
    
    Args:
        element_finder: Function that returns the element if found
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds
        message: Error message if timeout occurs
        
    Returns:
        True if element is not present, False if timeout occurred
    """
    if message is None:
        message = "Element still present within timeout period"
        
    def check_element_not_present():
        try:
            element = element_finder()
            return True if element is None else False
        except Exception:
            return True
            
    success, _ = await wait_until(
        condition=check_element_not_present,
        timeout=timeout,
        interval=interval,
        message=message,
        ignore_exceptions=True
    )
    return success

async def wait_with_backoff(
    condition: Callable[[], bool],
    max_attempts: int = 5,
    initial_wait: float = 1.0,
    backoff_factor: float = 2.0,
    max_wait: float = 30.0,
    message: str = "Condition not met after multiple attempts"
) -> bool:
    """
    Wait with exponential backoff between attempts.
    
    Args:
        condition: Function that returns True when condition is met
        max_attempts: Maximum number of attempts
        initial_wait: Initial wait time in seconds
        backoff_factor: Factor to increase wait time
        max_wait: Maximum wait time between attempts
        message: Error message if all attempts fail
        
    Returns:
        True if condition was met, False if all attempts failed
    """
    wait_time = initial_wait
    
    for attempt in range(1, max_attempts + 1):
        try:
            logger.debug(f"Attempt {attempt}/{max_attempts} with wait time {wait_time:.2f}s")
            
            if condition():
                return True
                
        except Exception as e:
            logger.warning(f"Exception during attempt {attempt}: {str(e)}")
            
        if attempt < max_attempts:
            # Wait before next attempt
            await asyncio.sleep(wait_time)
            
            # Increase wait time for next attempt
            wait_time = min(wait_time * backoff_factor, max_wait)
            
    logger.warning(f"All {max_attempts} attempts failed: {message}")
    return False

async def sleep(seconds: float) -> None:
    """
    Sleep for the specified number of seconds.
    
    Args:
        seconds: Number of seconds to sleep
    """
    await asyncio.sleep(seconds)

async def wait_for_animation(
    check_stability: Callable[[], bool] = None,
    timeout: float = 5.0,
    stability_duration: float = 0.5,
    interval: float = 0.1
) -> bool:
    """
    Wait for animations to complete by checking UI stability.
    
    Args:
        check_stability: Function that returns True when UI is stable
        timeout: Maximum time to wait in seconds
        stability_duration: Time UI must be stable for
        interval: Time between stability checks
        
    Returns:
        True if UI became stable, False if timeout occurred
    """
    if check_stability is None:
        # Default implementation just waits for a fixed time
        await asyncio.sleep(timeout)
        return True
        
    start_time = time.time()
    stable_since = None
    
    while time.time() - start_time < timeout:
        try:
            if check_stability():
                # UI is currently stable
                if stable_since is None:
                    # First time we've seen stability
                    stable_since = time.time()
                elif time.time() - stable_since >= stability_duration:
                    # UI has been stable for required duration
                    return True
            else:
                # UI is not stable, reset the stable_since time
                stable_since = None
        except Exception:
            # Error during stability check, assume not stable
            stable_since = None
            
        # Wait before next check
        await asyncio.sleep(interval)
        
    return False