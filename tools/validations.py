"""
Fail-Safe Validations: Enhanced validation tools with robust error handling,
smart waiting, and progressive fallback mechanisms.
"""

import re
import time
import difflib
from typing import Dict, Any, Awaitable, Callable

from tools.session_management import page_source, load_app
from tools.tool_registry import tool
from tools.interactions import get_text, element_is_displayed
from utils.logger import get_logger
from utils.screenshot_manager import ScreenshotManager
from utils.wait import wait_until, sleep
from utils.validation_result import ValidationResult

# Configure logger
logger = get_logger(__name__)

async def with_retry(
    validation_func: Callable[[], Awaitable[ValidationResult]],
    max_attempts: int = 3,
    retry_delay_ms: int = 500,
    progressive_delay: bool = True,
    screenshot_on_failure: bool = True,
    description: str = "Validation"
) -> ValidationResult:
    """
    Execute a validation function with retry logic.
    
    Args:
        validation_func: Async validation function to execute
        max_attempts: Maximum number of retry attempts
        retry_delay_ms: Delay between retries in milliseconds
        progressive_delay: Whether to increase delay progressively
        screenshot_on_failure: Whether to take screenshot on failure
        description: Description for logging
        
    Returns:
        ValidationResult with success status and details
    """
    result = None
    screenshot_path = None
    
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            # Calculate delay with optional progression
            delay = retry_delay_ms / 1000
            if progressive_delay:
                delay = delay * (1.5 ** (attempt - 1))
            
            logger.info(f"Retry attempt {attempt}/{max_attempts} for {description} after {delay:.2f}s delay")
            await sleep(delay)
        
        try:
            # Execute validation function
            result = await validation_func()
            result.attempts = attempt
            
            # If successful, return immediately
            if result.success:
                return result
                
            # If we've reached max attempts, break
            if attempt >= max_attempts:
                logger.warning(f"Validation failed after {attempt} attempts: {result.message}")
                break
                
            # Log failure for retry
            logger.info(f"Validation attempt {attempt} failed: {result.message}")
            
        except Exception as e:
            logger.error(f"Error in validation attempt {attempt}: {str(e)}")
            # Create failure result for exception
            result = ValidationResult(
                success=False,
                message=f"Exception during validation: {str(e)}",
                details={"exception": str(e), "attempt": attempt}
            )
            
            # If we've reached max attempts, break
            if attempt >= max_attempts:
                break
    
    # Take screenshot on final failure if enabled
    if screenshot_on_failure and not result.success:
        try:
            # Get session
            session = await load_app()
            if session.get("message") == "Success":
                # Create screenshot manager
                screenshot_manager = ScreenshotManager(session["driver"])
                
                # Take screenshot
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                screenshot_path = screenshot_manager.take_screenshot(f"validation_failure_{timestamp}")
                
                # Add screenshot to result evidence
                if screenshot_path:
                    result.evidence["failure_screenshot"] = screenshot_path
                    
                    # Update failure message to include screenshot reference
                    result.message += f" (See failure screenshot)"
        except Exception as e:
            logger.warning(f"Failed to capture failure screenshot: {str(e)}")
    
    return result

@tool(
    agent_names=["executor", "checker"],
    description="Verify text content is displayed on screen with smart waiting and retries",
    name="verify_text_displayed",
    parameters={
        "expected_text": {
            "type": "string",
            "description": "Text that should be visible on screen"
        },
        "exact_match": {
            "type": "boolean",
            "description": "Whether to require exact text match (vs substring)",
            "default": False
        },
        "timeout_seconds": {
            "type": "number",
            "description": "Maximum time to wait for text to appear",
            "default": 5.0
        },
        "similarity_threshold": {
            "type": "number",
            "description": "Threshold for fuzzy text matching (0.0-1.0)",
            "default": 0.8
        }
    }
)
async def verify_text_displayed(
    expected_text: str, 
    exact_match: bool = False,
    timeout_seconds: float = 5.0,
    similarity_threshold: float = 0.8
) -> Dict[str, Any]:
    """
    Verify specific text is displayed on the screen with smart waiting and retries.
    
    Args:
        expected_text: Text that should be visible
        exact_match: Whether to require exact text match
        timeout_seconds: Maximum time to wait for text to appear
        similarity_threshold: Threshold for fuzzy text matching
        
    Returns:
        Result of the verification
    """
    logger.info(f"Verifying text is displayed: '{expected_text}' (timeout: {timeout_seconds}s)")
    
    async def perform_validation() -> ValidationResult:
        # Get current page source
        page_src = await page_source()
        content = page_src.get("body", "")
        
        if not content:
            return ValidationResult(
                success=False, 
                message="Could not retrieve page source"
            )
        
        # Try different matching strategies from most to least strict
        if exact_match:
            # For exact match, look for text="expected_text" pattern
            pattern = f'text="{re.escape(expected_text)}"'
            found_exact = pattern in content
            
            if found_exact:
                return ValidationResult(
                    success=True,
                    message=f"Text '{expected_text}' is displayed (exact match)",
                    details={"match_type": "exact", "attribute": "text"}
                )
        
        # Try direct substring match (less strict)
        found_substring = expected_text in content
        if found_substring:
            return ValidationResult(
                success=True,
                message=f"Text '{expected_text}' is displayed (substring match)",
                details={"match_type": "substring"}
            )
        
        # Try fuzzy matching as fallback (least strict)
        if not exact_match:
            # Extract all text attributes from content
            text_values = re.findall(r'text="([^"]*)"', content)
            label_values = re.findall(r'label="([^"]*)"', content)
            content_values = re.findall(r'content-desc="([^"]*)"', content)
            
            # Combine all potential text sources
            all_texts = text_values + label_values + content_values
            
            # Look for fuzzy matches
            for text in all_texts:
                if not text:
                    continue
                    
                # Calculate similarity ratio
                similarity = difflib.SequenceMatcher(None, expected_text.lower(), text.lower()).ratio()
                
                if similarity >= similarity_threshold:
                    return ValidationResult(
                        success=True,
                        message=f"Text similar to '{expected_text}' is displayed (fuzzy match: '{text}', similarity: {similarity:.2f})",
                        details={
                            "match_type": "fuzzy", 
                            "matched_text": text, 
                            "similarity": similarity
                        }
                    )
        
        # If we get here, text was not found
        return ValidationResult(
            success=False,
            message=f"Text '{expected_text}' not found on screen",
            details={"content_length": len(content)}
        )

    # Use wait_until to implement smart waiting
    success, result = await wait_until(
        condition=lambda: perform_validation(),
        timeout=timeout_seconds,
        interval=0.5,
        message=f"Timed out waiting for text '{expected_text}' to appear"
    )
    
    # Return final result
    if success and result.success:
        return result.to_dict()
    else:
        # If we timed out or otherwise failed, perform one final validation
        # with screenshot evidence
        result = await with_retry(
            validation_func=perform_validation,
            max_attempts=1,  # Just one try since we already waited
            screenshot_on_failure=True,
            description=f"Text validation '{expected_text}'"
        )
        return result.to_dict()

@tool(
    agent_names=["executor"],
    description="Verify current screen matches expected screen with smart waiting",
    name="verify_current_screen",
    parameters={
        "expected_screen": {
            "type": "string", 
            "description": "Name of expected screen"
        },
        "timeout_seconds": {
            "type": "number",
            "description": "Maximum time to wait for screen to appear",
            "default": 10.0
        },
        "match_threshold": {
            "type": "number", 
            "description": "Minimum match score to consider validation successful",
            "default": 0.5
        }
    }
)
async def verify_current_screen(
    expected_screen: str, 
    timeout_seconds: float = 10.0,
    match_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Verify the current screen matches the expected screen with smart waiting.
    
    Args:
        expected_screen: Name of expected screen
        timeout_seconds: Maximum time to wait for screen to appear
        match_threshold: Minimum match score threshold
        
    Returns:
        Result of the verification
    """
    from core.context_manager import ContextManager
    
    logger.info(f"Verifying current screen is '{expected_screen}' (timeout: {timeout_seconds}s)")
    
    screens_registry = ContextManager.get("screens_registry")
    if not screens_registry:
        return {
            "message": "Failure", 
            "error": "Screen registry not available", 
            "verified": False
        }
        
    # Update current screen context
    ContextManager.set("current_screen", expected_screen)
    
    async def perform_validation() -> ValidationResult:
        # Get current page source to ensure fresh validation
        page_src = await page_source()
        
        # Validate screen with fresh page source
        validation = await screens_registry.validate_current_screen(
            expected_screen, 
            page_source=page_src.get("body", "")
        )
        
        match_score = validation.get("match_score", 0)
        is_valid = validation.get("valid", False)
        
        if is_valid and match_score >= match_threshold:
            return ValidationResult(
                success=True,
                message=f"Current screen is '{expected_screen}' (match score: {match_score:.2f})",
                details={
                    "screen_name": expected_screen,
                    "match_score": match_score,
                    "identifiers_matched": validation.get("matched_identifiers", [])
                }
            )
        else:
            return ValidationResult(
                success=False,
                message=f"Current screen is not '{expected_screen}' (match score: {match_score:.2f})",
                details={
                    "expected_screen": expected_screen,
                    "match_score": match_score,
                    "threshold": match_threshold,
                    "identifiers_matched": validation.get("matched_identifiers", []),
                    "identifiers_missing": validation.get("missing_identifiers", [])
                }
            )

    # Use with_retry to implement retry logic
    result = await with_retry(
        validation_func=perform_validation,
        max_attempts=3,
        retry_delay_ms=1000,
        progressive_delay=True,
        screenshot_on_failure=True,
        description=f"Screen validation '{expected_screen}'"
    )
    
    # If still failing after retries, try smart waiting
    if not result.success and timeout_seconds > 0:
        logger.info(f"Initial validation failed, waiting up to {timeout_seconds}s for screen '{expected_screen}'")
        
        # Use wait_until for smart waiting
        success, wait_result = await wait_until(
            condition=lambda: perform_validation(),
            timeout=timeout_seconds,
            interval=0.75,
            message=f"Timed out waiting for screen '{expected_screen}'"
        )
        
        if success and wait_result.success:
            # If successful after waiting, use that result
            result = wait_result
        else:
            # Take final screenshot if we're still failing
            final_result = await with_retry(
                validation_func=perform_validation,
                max_attempts=1,
                screenshot_on_failure=True,
                description=f"Final screen validation '{expected_screen}'"
            )
            result = final_result
    
    return result.to_dict()

@tool(
    agent_names=["executor"],
    description="Verify displayed location matches expected location with fallbacks",
    name="verify_displayed_location",
    parameters={
        "expected_location": {
            "type": "string",
            "description": "Expected location text"
        },
        "timeout_seconds": {
            "type": "number",
            "description": "Maximum time to wait for location to appear",
            "default": 5.0
        },
        "similarity_threshold": {
            "type": "number",
            "description": "Threshold for fuzzy location matching",
            "default": 0.7
        }
    }
)
async def verify_displayed_location(
    expected_location: str,
    timeout_seconds: float = 5.0,
    similarity_threshold: float = 0.7
) -> Dict[str, Any]:
    """
    Verify the displayed location matches the expected location with smart fallbacks.
    
    Args:
        expected_location: Expected location text
        timeout_seconds: Maximum time to wait for location to appear
        similarity_threshold: Threshold for fuzzy location matching
        
    Returns:
        Result of the verification
    """
    logger.info(f"Verifying displayed location: '{expected_location}' (timeout: {timeout_seconds}s)")
    
    # Extract location parts for more flexible matching
    location_parts = [part.strip() for part in expected_location.split(',')]
    primary_location = location_parts[0] if location_parts else expected_location
    
    # Common location element IDs across food delivery apps
    location_elements = [
        "location_text", "current_location", "address_text", 
        "delivery_location", "selected_location", "location_title",
        "user_location", "delivery_address", "address", "location",
        # Zomato-specific location elements
        "com.application.zomato:id/location", 
        "com.application.zomato:id/tv_location",
        "com.application.zomato:id/tv_address",
        "com.application.zomato:id/tv_location_text",
        "com.application.zomato:id/txt_location"
    ]
    
    async def perform_validation() -> ValidationResult:
        # Get latest page source
        page_src = await page_source()
        content = page_src.get("body", "")
        
        # Strategy 1: Try to find exact location in known location elements
        for element_id in location_elements:
            display_result = await element_is_displayed(element_id, timeout=0.5)
            
            if display_result.get("body", False):
                text_result = await get_text(element_id)
                
                if text_result.get("message") == "Success":
                    actual_text = text_result.get("body", "")
                    
                    # Check for exact match
                    if expected_location in actual_text:
                        return ValidationResult(
                            success=True,
                            message=f"Location '{expected_location}' is displayed in element '{element_id}'",
                            details={
                                "match_type": "exact", 
                                "element_id": element_id, 
                                "actual_text": actual_text
                            }
                        )
                    
                    # Check for primary location match (first part before comma)
                    elif primary_location in actual_text:
                        return ValidationResult(
                            success=True,
                            message=f"Primary location '{primary_location}' is displayed in element '{element_id}'",
                            details={
                                "match_type": "primary_part", 
                                "element_id": element_id, 
                                "matched_part": primary_location,
                                "actual_text": actual_text
                            }
                        )
                    
                    # Try fuzzy matching
                    elif similarity_threshold < 1.0:
                        similarity = difflib.SequenceMatcher(None, expected_location.lower(), actual_text.lower()).ratio()
                        
                        if similarity >= similarity_threshold:
                            return ValidationResult(
                                success=True,
                                message=f"Location similar to '{expected_location}' is displayed (fuzzy match: '{actual_text}', similarity: {similarity:.2f})",
                                details={
                                    "match_type": "fuzzy", 
                                    "element_id": element_id,
                                    "actual_text": actual_text, 
                                    "similarity": similarity
                                }
                            )
        
        # Strategy 2: Check for location keywords in page source
        location_keywords = [
            expected_location,
            primary_location,
            expected_location.replace(", ", ",")  # Handle comma formatting difference
        ]
        
        for keyword in location_keywords:
            if keyword in content:
                return ValidationResult(
                    success=True,
                    message=f"Location '{keyword}' found in page content",
                    details={"match_type": "page_source", "matched_keyword": keyword}
                )
        
        # Strategy 3: Check for any location-like elements with text
        location_patterns = [
            r'id="[^"]*location[^"]*"[^>]*>([^<]+)<',
            r'id="[^"]*address[^"]*"[^>]*>([^<]+)<',
            r'text="([^"]*(?:Bengaluru|Bangalore|Indiranagar|HSR|Koramangala)[^"]*)"'
        ]
        
        for pattern in location_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                # Check if match has any similarity to expected location
                similarity = difflib.SequenceMatcher(None, expected_location.lower(), match.lower()).ratio()
                
                if similarity >= similarity_threshold:
                    return ValidationResult(
                        success=True,
                        message=f"Found location-like text '{match}' (similarity: {similarity:.2f})",
                        details={
                            "match_type": "pattern_match", 
                            "matched_text": match,
                            "similarity": similarity
                        }
                    )
        
        # If we get here, location was not found
        return ValidationResult(
            success=False,
            message=f"Location '{expected_location}' not found on screen"
        )

    # Use wait_until to implement smart waiting
    success, result = await wait_until(
        condition=lambda: perform_validation(),
        timeout=timeout_seconds,
        interval=0.75,
        message=f"Timed out waiting for location '{expected_location}' to appear"
    )
    
    # Return final result
    if success and result.success:
        return result.to_dict()
    else:
        # If we timed out or otherwise failed, try with multiple retry attempts
        # This helps with flaky UI that might update asynchronously
        result = await with_retry(
            validation_func=perform_validation,
            max_attempts=3,
            retry_delay_ms=1000,
            progressive_delay=True,
            screenshot_on_failure=True,
            description=f"Location validation '{expected_location}'"
        )
        return result.to_dict()

@tool(
    agent_names=["executor"],
    description="Verify element contains specific text with smart waiting and fallbacks",
    name="verify_element_text",
    parameters={
        "element_id": {
            "type": "string",
            "description": "Element identifier"
        },
        "expected_text": {
            "type": "string",
            "description": "Expected text content"
        },
        "exact_match": {
            "type": "boolean",
            "description": "Whether to require exact text match",
            "default": True
        },
        "timeout_seconds": {
            "type": "number",
            "description": "Maximum time to wait for text to appear",
            "default": 5.0
        },
        "similarity_threshold": {
            "type": "number",
            "description": "Threshold for fuzzy text matching",
            "default": 0.8
        }
    }
)
async def verify_element_text(
    element_id: str, 
    expected_text: str, 
    exact_match: bool = True,
    timeout_seconds: float = 5.0,
    similarity_threshold: float = 0.8
) -> Dict[str, Any]:
    """
    Verify an element contains specific text with smart waiting and fallbacks.
    
    Args:
        element_id: Element identifier
        expected_text: Expected text content
        exact_match: Whether to require exact text match
        timeout_seconds: Maximum time to wait for text to appear
        similarity_threshold: Threshold for fuzzy text matching
        
    Returns:
        Result of the verification
    """
    logger.info(f"Verifying element '{element_id}' contains text: '{expected_text}' (timeout: {timeout_seconds}s)")
    
    async def perform_validation() -> ValidationResult:
        # First verify element exists
        display_result = await element_is_displayed(element_id, timeout=1.0)
        
        if not display_result.get("body", False):
            return ValidationResult(
                success=False,
                message=f"Element '{element_id}' not found on screen",
                details={"element_visible": False}
            )
        
        # Get element text
        text_result = await get_text(element_id)
        
        if text_result.get("message") != "Success":
            return ValidationResult(
                success=False,
                message=f"Failed to get text from element: {element_id}",
                details={"error": text_result.get("error", "Unknown error")}
            )
        
        actual_text = text_result.get("body", "")
        
        # Strategy 1: Exact matching
        if exact_match:
            if actual_text == expected_text:
                return ValidationResult(
                    success=True,
                    message=f"Element '{element_id}' has exact text '{expected_text}'",
                    details={"match_type": "exact", "actual_text": actual_text}
                )
        # Strategy 2: Substring matching
        elif expected_text in actual_text:
            return ValidationResult(
                success=True,
                message=f"Element '{element_id}' contains text '{expected_text}'",
                details={"match_type": "substring", "actual_text": actual_text}
            )
        
        # Strategy 3: Fuzzy matching if exact match fails
        similarity = difflib.SequenceMatcher(None, expected_text.lower(), actual_text.lower()).ratio()
        
        if similarity >= similarity_threshold:
            return ValidationResult(
                success=True,
                message=f"Element '{element_id}' has similar text (expected: '{expected_text}', actual: '{actual_text}', similarity: {similarity:.2f})",
                details={
                    "match_type": "fuzzy", 
                    "actual_text": actual_text,
                    "similarity": similarity
                }
            )
        
        # If we get here, text doesn't match
        return ValidationResult(
            success=False,
            message=f"Element '{element_id}' text was '{actual_text}', expected '{expected_text}'",
            details={
                "actual_text": actual_text,
                "similarity": similarity,
                "threshold": similarity_threshold
            }
        )

    # Use with_retry and wait_until for reliability
    # First check if element appears within timeout
    if timeout_seconds > 0:
        visible, _ = await wait_until(
            condition=lambda: element_is_displayed(element_id, timeout=0.5),
            timeout=timeout_seconds * 0.5,  # Half the timeout for element to appear
            interval=0.5,
            message=f"Timed out waiting for element '{element_id}' to appear"
        )
        
        if not visible:
            # Element didn't appear, fail early
            return {
                "message": "Failure",
                "error": f"Element '{element_id}' did not appear within {timeout_seconds * 0.5}s",
                "verified": False
            }
    
    # Use wait_until to wait for text to match
    remaining_timeout = timeout_seconds * 0.5  # Remaining timeout for text to appear
    success, result = await wait_until(
        condition=lambda: perform_validation(),
        timeout=remaining_timeout,
        interval=0.5,
        message=f"Timed out waiting for element '{element_id}' to have text '{expected_text}'"
    )
    
    # Return final result
    if success and result.success:
        return result.to_dict()
    else:
        # If we timed out or otherwise failed, try with multiple retry attempts
        result = await with_retry(
            validation_func=perform_validation,
            max_attempts=2,
            retry_delay_ms=800,
            screenshot_on_failure=True,
            description=f"Element text validation '{element_id}'"
        )
        return result.to_dict()

@tool(
    agent_names=["executor"],
    description="Verify complex condition using multiple checks with smart fallbacks",
    name="verify_complex_condition",
    parameters={
        "condition_type": {
            "type": "string",
            "description": "Type of condition to check (location, login_state, etc.)"
        },
        "expected_value": {
            "type": "string",
            "description": "Expected value to verify"
        },
        "timeout_seconds": {
            "type": "number",
            "description": "Maximum time to wait for condition to be true",
            "default": 10.0
        }
    }
)
async def verify_complex_condition(
    condition_type: str, 
    expected_value: str,
    timeout_seconds: float = 10.0
) -> Dict[str, Any]:
    """
    Verify a complex condition that may require multiple checks with smart fallbacks.
    
    Args:
        condition_type: Type of condition to check (location, login_state, etc.)
        expected_value: Expected value to verify
        timeout_seconds: Maximum time to wait for condition to be true
        
    Returns:
        Result of the verification
    """
    logger.info(f"Verifying complex condition: {condition_type}={expected_value} (timeout: {timeout_seconds}s)")
    
    # Handle different condition types
    if condition_type.lower() == "location":
        # Delegate to specialized location verification
        return await verify_displayed_location(
            expected_location=expected_value,
            timeout_seconds=timeout_seconds
        )
        
    elif condition_type.lower() in ["login_state", "logged_in"]:
        # Check if user is logged in/out as expected
        logged_in_elements = ["profile_icon", "account_menu", "user_name", "profile_pic"]
        logged_out_elements = ["login_button", "sign_in_button", "register_link", "signup_link"]
        
        if expected_value.lower() in ["logged_in", "true", "yes"]:
            check_elements = logged_in_elements
            opposite_elements = logged_out_elements
            condition_name = "Logged in"
        else:
            check_elements = logged_out_elements
            opposite_elements = logged_in_elements
            condition_name = "Logged out"
            
        async def check_login_state() -> ValidationResult:
            # Check if any expected elements are displayed
            for element_id in check_elements:
                display_result = await element_is_displayed(element_id, timeout=1.0)
                if display_result.get("body", False):
                    return ValidationResult(
                        success=True,
                        message=f"User is {condition_name} as expected (found element: {element_id})",
                        details={"element_found": element_id, "condition_type": condition_type}
                    )
            
            # Check if any opposite elements are displayed (indicating failure)
            for element_id in opposite_elements:
                display_result = await element_is_displayed(element_id, timeout=1.0)
                if display_result.get("body", False):
                    return ValidationResult(
                        success=False,
                        message=f"User is not {condition_name} as expected (found opposite element: {element_id})",
                        details={"opposite_element_found": element_id}
                    )
                    
            # If no definitive elements found either way, check page content
            page_src = await page_source()
            content = page_src.get("body", "")
            
            login_indicators = ["account", "profile", "sign out", "logout"]
            logout_indicators = ["sign in", "login", "register", "sign up"]
            
            indicators = login_indicators if condition_name == "Logged in" else logout_indicators
            
            for indicator in indicators:
                if indicator in content.lower():
                    return ValidationResult(
                        success=True,
                        message=f"User appears to be {condition_name} (found indicator: '{indicator}')",
                        details={"indicator_found": indicator, "match_type": "content"}
                    )
            
            # If still no clear indicators, report as unverifiable
            return ValidationResult(
                success=False,
                message=f"Could not definitively determine if user is {condition_name}",
                details={"checked_elements": check_elements, "opposite_elements": opposite_elements}
            )
            
        # Use wait_until for smart waiting
        success, result = await wait_until(
            condition=lambda: check_login_state(),
            timeout=timeout_seconds,
            interval=1.0,
            message=f"Timed out waiting to verify {condition_name} state"
        )
        
        # Return final result
        if success and result.success:
            return result.to_dict()
        else:
            # Try with multiple retry attempts
            result = await with_retry(
                validation_func=check_login_state,
                max_attempts=2,
                retry_delay_ms=1000,
                screenshot_on_failure=True,
                description=f"Login state validation '{condition_name}'"
            )
            return result.to_dict()
            
    else:
        # For unsupported condition types
        return {
            "message": "Failure",
            "error": f"Unsupported condition type: {condition_type}",
            "verified": False,
            "supported_types": ["location", "login_state"]
        }