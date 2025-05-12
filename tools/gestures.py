"""
Gestures: Touch interaction tools for mobile testing using W3C Actions API.

This module provides tools for various touch gestures like tap, swipe, scroll,
and more for mobile app testing, using the W3C Actions API supported by Appium 2.0+.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple, Union

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.common.exceptions import NoSuchElementException, WebDriverException

from interaction.element_finder import element_finder, find_element
from tools.session_management import load_app
from tools.tool_registry import tool
from utils.logger import get_logger
from core.error_handler import handle_error

# Configure logger
logger = get_logger(__name__)

@tool(
    agent_names=["executor", "checker"],
    description="Single tap on an element",
    name="single_tap",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier (ID, text, etc.)"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the tap operation"
    }
)
async def single_tap(search_key: str) -> Dict[str, Any]:
    """
    Single tap on an element using W3C Actions API.
    
    Args:
        search_key: Element identifier (ID, text, etc.)
        
    Returns:
        Result of the tap operation
    """
    logger.info(f"Single tap on element: {search_key}")
    
    try:
        # Find the element
        element = await find_element(search_key)
        if not element:
            return {"message": "Failure", "error": f"Element not found: {search_key}"}
        
        # Get session
        session = await load_app()
        if session.get("message") != "Success":
            return session
        
        driver = session["driver"]
        
        # Create pointer input for touch
        actions = ActionChains(driver)
        actions.click(element)
        actions.perform()
        
        return {"message": "Success", "details": f"Tapped on {search_key}"}
    except Exception as e:
        error_details = handle_error(e, f"Failed to tap on element: {search_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Double tap on an element",
    name="double_tap",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier (ID, text, etc.)"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the double tap operation"
    }
)
async def double_tap(search_key: str) -> Dict[str, Any]:
    """
    Double tap on an element using W3C Actions API.
    
    Args:
        search_key: Element identifier (ID, text, etc.)
        
    Returns:
        Result of the double tap operation
    """
    logger.info(f"Double tap on element: {search_key}")
    
    try:
        # Find the element
        element = await find_element(search_key)
        if not element:
            return {"message": "Failure", "error": f"Element not found: {search_key}"}
        
        # Get session
        session = await load_app()
        if session.get("message") != "Success":
            return session
        
        driver = session["driver"]
        
        # Create pointer input for touch
        actions = ActionChains(driver)
        actions.double_click(element)
        actions.perform()
        
        return {"message": "Success", "details": f"Double-tapped on {search_key}"}
    except Exception as e:
        error_details = handle_error(e, f"Failed to double tap on element: {search_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Long press on an element",
    name="long_press",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier (ID, text, etc.)"
        },
        "duration_ms": {
            "type": "integer",
            "description": "Duration of the long press in milliseconds",
            "default": 1000
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the long press operation"
    }
)
async def long_press(search_key: str, duration_ms: int = 1000) -> Dict[str, Any]:
    """
    Long press on an element using W3C Actions API.
    
    Args:
        search_key: Element identifier (ID, text, etc.)
        duration_ms: Duration of the long press in milliseconds
        
    Returns:
        Result of the long press operation
    """
    logger.info(f"Long press on element: {search_key} for {duration_ms}ms")
    
    try:
        # Find the element
        element = await find_element(search_key)
        if not element:
            return {"message": "Failure", "error": f"Element not found: {search_key}"}
        
        # Get session
        session = await load_app()
        if session.get("message") != "Success":
            return session
        
        driver = session["driver"]
        
        # Create pointer input for touch
        actions = ActionChains(driver)
        actions.click_and_hold(element)
        actions.pause(duration_ms / 1000)  # Convert ms to seconds
        actions.release()
        actions.perform()
        
        return {"message": "Success", "details": f"Long-pressed on {search_key} for {duration_ms}ms"}
    except Exception as e:
        error_details = handle_error(e, f"Failed to long press on element: {search_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Swipe from one point to another",
    name="swipe",
    parameters={
        "direction": {
            "type": "string",
            "description": "Direction to swipe (up, down, left, right)",
            "default": "up"
        },
        "start_x": {
            "type": "integer",
            "description": "Starting X coordinate (optional)",
            "default": None
        },
        "start_y": {
            "type": "integer",
            "description": "Starting Y coordinate (optional)",
            "default": None
        },
        "end_x": {
            "type": "integer",
            "description": "Ending X coordinate (optional)",
            "default": None
        },
        "end_y": {
            "type": "integer",
            "description": "Ending Y coordinate (optional)",
            "default": None
        },
        "duration_ms": {
            "type": "integer",
            "description": "Duration of the swipe in milliseconds",
            "default": 500
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the swipe operation"
    }
)
async def swipe(
    direction: str = "up",
    start_x: Optional[int] = None,
    start_y: Optional[int] = None,
    end_x: Optional[int] = None,
    end_y: Optional[int] = None,
    duration_ms: int = 500
) -> Dict[str, Any]:
    """
    Swipe from one point to another using W3C Actions API.
    
    Args:
        direction: Direction to swipe (up, down, left, right)
        start_x: Starting X coordinate (optional)
        start_y: Starting Y coordinate (optional)
        end_x: Ending X coordinate (optional)
        end_y: Ending Y coordinate (optional)
        duration_ms: Duration of the swipe in milliseconds
        
    Returns:
        Result of the swipe operation
    """
    logger.info(f"Swiping {direction}")
    
    try:
        # Get session
        session = await load_app()
        if session.get("message") != "Success":
            return session
        
        driver = session["driver"]
        window_size = driver.get_window_size()
        screen_width = window_size["width"]
        screen_height = window_size["height"]
        
        # Calculate coordinates based on direction if not provided
        if start_x is None or start_y is None or end_x is None or end_y is None:
            if direction.lower() == "up":
                start_x = screen_width // 2
                start_y = screen_height * 3 // 4
                end_x = screen_width // 2
                end_y = screen_height // 4
            elif direction.lower() == "down":
                start_x = screen_width // 2
                start_y = screen_height // 4
                end_x = screen_width // 2
                end_y = screen_height * 3 // 4
            elif direction.lower() == "left":
                start_x = screen_width * 3 // 4
                start_y = screen_height // 2
                end_x = screen_width // 4
                end_y = screen_height // 2
            elif direction.lower() == "right":
                start_x = screen_width // 4
                start_y = screen_height // 2
                end_x = screen_width * 3 // 4
                end_y = screen_height // 2
            else:
                return {"message": "Failure", "error": f"Unknown swipe direction: {direction}"}
        
        # Create W3C Actions for swipe
        finger_input = PointerInput(interaction.POINTER_TOUCH, "finger")
        action = ActionChains(driver)
        action.w3c_actions = ActionBuilder(driver, mouse=finger_input)
        
        # Calculate number of steps (higher number = smoother)
        steps = max(1, int(duration_ms / 50))
        
        # Create action sequence
        action.w3c_actions.pointer_action.move_to_location(start_x, start_y)
        action.w3c_actions.pointer_action.pointer_down()
        
        # Calculate intermediate points for a smoother motion
        for i in range(1, steps + 1):
            time_fraction = i / steps
            current_x = start_x + (end_x - start_x) * time_fraction
            current_y = start_y + (end_y - start_y) * time_fraction
            action.w3c_actions.pointer_action.move_to_location(
                round(current_x), round(current_y)
            )
            action.w3c_actions.pointer_action.pause(duration_ms / (steps * 1000))
        
        action.w3c_actions.pointer_action.release()
        action.perform()
        
        return {
            "message": "Success", 
            "details": f"Swiped {direction} from ({start_x},{start_y}) to ({end_x},{end_y})"
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to swipe {direction}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Scroll until an element is visible",
    name="scroll_to_element",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier to scroll to (ID, text, etc.)"
        },
        "direction": {
            "type": "string",
            "description": "Direction to scroll (up, down, left, right)",
            "default": "down"
        },
        "max_swipes": {
            "type": "integer",
            "description": "Maximum number of swipes to attempt",
            "default": 10
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the scroll operation"
    }
)
async def scroll_to_element(
    search_key: str,
    direction: str = "down",
    max_swipes: int = 10
) -> Dict[str, Any]:
    """
    Scroll until an element is visible.
    
    Args:
        search_key: Element identifier to scroll to (ID, text, etc.)
        direction: Direction to scroll (up, down, left, right)
        max_swipes: Maximum number of swipes to attempt
        
    Returns:
        Result of the scroll operation
    """
    logger.info(f"Scrolling to find element: {search_key}")
    
    try:
        # Get session
        session = await load_app()
        if session.get("message") != "Success":
            return session
            
        driver = session["driver"]
        
        # First check if element is already visible
        element = await find_element(search_key, timeout=1.0)
        if element:
            return {"message": "Success", "details": f"Element {search_key} already visible"}
            
        # Try platform-specific scrolling first
        if await _try_platform_scroll(driver, search_key):
            return {"message": "Success", "details": f"Scrolled to {search_key} using platform-specific method"}
            
        # Fall back to manual scrolling
        for i in range(max_swipes):
            # Check if element is visible after each swipe
            element = await find_element(search_key, timeout=1.0)
            if element:
                return {"message": "Success", "details": f"Found {search_key} after {i} swipes"}
                
            # Perform a swipe
            swipe_result = await swipe(direction=direction)
            if swipe_result.get("message") != "Success":
                return swipe_result
                
            # Small pause to let content settle
            await asyncio.sleep(0.5)
            
        # One last check
        element = await find_element(search_key, timeout=1.0)
        if element:
            return {"message": "Success", "details": f"Found {search_key} after final check"}
            
        return {"message": "Failure", "error": f"Element {search_key} not found after {max_swipes} swipes"}
    except Exception as e:
        error_details = handle_error(e, f"Failed to scroll to element: {search_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Drag and drop an element to a target position",
    name="drag_and_drop",
    parameters={
        "source_key": {
            "type": "string",
            "description": "Source element identifier (ID, text, etc.)"
        },
        "target_key": {
            "type": "string",
            "description": "Target element identifier (ID, text, etc.)"
        },
        "duration_ms": {
            "type": "integer",
            "description": "Duration of the drag in milliseconds",
            "default": 1000
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the drag and drop operation"
    }
)
async def drag_and_drop(
    source_key: str,
    target_key: str,
    duration_ms: int = 1000
) -> Dict[str, Any]:
    """
    Drag and drop an element to a target position using W3C Actions API.
    
    Args:
        source_key: Source element identifier (ID, text, etc.)
        target_key: Target element identifier (ID, text, etc.)
        duration_ms: Duration of the drag in milliseconds
        
    Returns:
        Result of the drag and drop operation
    """
    logger.info(f"Drag and drop from {source_key} to {target_key}")
    
    try:
        # Get session
        session = await load_app()
        if session.get("message") != "Success":
            return session
            
        driver = session["driver"]
        
        # Find source and target elements
        source_element = await find_element(source_key)
        if not source_element:
            return {"message": "Failure", "error": f"Source element not found: {source_key}"}
            
        target_element = await find_element(target_key)
        if not target_element:
            return {"message": "Failure", "error": f"Target element not found: {target_key}"}
        
        # Create action for drag and drop using W3C Actions API
        action = ActionChains(driver)
        action.drag_and_drop(source_element, target_element)
        action.perform()
        
        return {
            "message": "Success",
            "details": f"Dragged from {source_key} to {target_key}"
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to drag and drop from {source_key} to {target_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Pinch or zoom on the screen",
    name="pinch_zoom",
    parameters={
        "action": {
            "type": "string",
            "description": "Action to perform (pinch or zoom)",
            "default": "zoom"
        },
        "x": {
            "type": "integer",
            "description": "Center X coordinate of the pinch/zoom",
            "default": None
        },
        "y": {
            "type": "integer",
            "description": "Center Y coordinate of the pinch/zoom",
            "default": None
        },
        "scale": {
            "type": "number",
            "description": "Scale factor (0.5 for pinch, 2.0 for zoom)",
            "default": 2.0
        },
        "duration_ms": {
            "type": "integer",
            "description": "Duration of the gesture in milliseconds",
            "default": 500
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the pinch/zoom operation"
    }
)
async def pinch_zoom(
    action: str = "zoom",
    x: Optional[int] = None,
    y: Optional[int] = None,
    scale: float = 2.0,
    duration_ms: int = 500
) -> Dict[str, Any]:
    """
    Pinch or zoom on the screen using W3C Actions API.
    
    Args:
        action: Action to perform (pinch or zoom)
        x: Center X coordinate of the pinch/zoom
        y: Center Y coordinate of the pinch/zoom
        scale: Scale factor (0.5 for pinch, 2.0 for zoom)
        duration_ms: Duration of the gesture in milliseconds
        
    Returns:
        Result of the pinch/zoom operation
    """
    logger.info(f"Performing {action} gesture")
    
    try:
        # Get session
        session = await load_app()
        if session.get("message") != "Success":
            return session
            
        driver = session["driver"]
        window_size = driver.get_window_size()
        
        # Use center of screen if coordinates not provided
        if x is None:
            x = window_size["width"] // 2
        if y is None:
            y = window_size["height"] // 2
            
        # Adjust scale based on action
        if action.lower() == "pinch":
            scale = 0.5 if scale >= 1.0 else scale
        else:  # zoom
            scale = 2.0 if scale <= 1.0 else scale
            
        # Calculate finger positions
        distance = min(window_size["width"], window_size["height"]) // 6
        
        # For W3C Actions API, we need two separate pointer inputs
        finger1 = PointerInput(interaction.POINTER_TOUCH, "finger1")
        finger2 = PointerInput(interaction.POINTER_TOUCH, "finger2")
        
        # Create two separate action chains
        actions = ActionBuilder(driver)
        actions.add_pointer_input(finger1)
        actions.add_pointer_input(finger2)
        
        # Calculate starting and ending positions for both fingers
        if action.lower() == "pinch":
            # For pinch, fingers start far and move inward
            finger1_start_x = x - distance
            finger1_start_y = y - distance
            finger2_start_x = x + distance
            finger2_start_y = y + distance
            
            finger1_end_x = x - (distance // 2)
            finger1_end_y = y - (distance // 2)
            finger2_end_x = x + (distance // 2)
            finger2_end_y = y + (distance // 2)
        else:  # zoom
            # For zoom, fingers start near and move outward
            finger1_start_x = x - (distance // 2)
            finger1_start_y = y - (distance // 2)
            finger2_start_x = x + (distance // 2)
            finger2_start_y = y + (distance // 2)
            
            finger1_end_x = x - (distance * scale)
            finger1_end_y = y - (distance * scale)
            finger2_end_x = x + (distance * scale)
            finger2_end_y = y + (distance * scale)
        
        # Define the actions for finger 1
        actions.pointer_action.pointer_inputs[0].create_pointer_move(
            duration=0,
            x=finger1_start_x,
            y=finger1_start_y
        )
        actions.pointer_action.pointer_inputs[0].create_pointer_down(
            button=0
        )
        actions.pointer_action.pointer_inputs[0].create_pointer_move(
            duration=duration_ms,
            x=finger1_end_x,
            y=finger1_end_y
        )
        actions.pointer_action.pointer_inputs[0].create_pointer_up(
            button=0
        )
        
        # Define the actions for finger 2
        actions.pointer_action.pointer_inputs[1].create_pointer_move(
            duration=0,
            x=finger2_start_x,
            y=finger2_start_y
        )
        actions.pointer_action.pointer_inputs[1].create_pointer_down(
            button=0
        )
        actions.pointer_action.pointer_inputs[1].create_pointer_move(
            duration=duration_ms,
            x=finger2_end_x,
            y=finger2_end_y
        )
        actions.pointer_action.pointer_inputs[1].create_pointer_up(
            button=0
        )
        
        # Perform the action
        actions.perform()
        
        return {
            "message": "Success",
            "details": f"Performed {action} gesture at ({x}, {y}) with scale {scale}"
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to perform {action} gesture")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

async def _try_platform_scroll(driver, search_key: str) -> bool:
    """
    Try platform-specific scrolling methods.
    
    Args:
        driver: Appium WebDriver instance
        search_key: Element identifier to scroll to
        
    Returns:
        True if successful, False otherwise
    """
    try:
        platform = element_finder.platform
        
        if platform == "android":
            # Try UiScrollable for Android (still supported)
            try:
                scroll_cmd = (
                    f'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView('
                    f'new UiSelector().textContains("{search_key}"))'
                )
                driver.find_element_by_android_uiautomator(scroll_cmd)
                logger.debug(f"Android UiScrollable successful for {search_key}")
                return True
            except Exception as e:
                logger.debug(f"Android UiScrollable failed: {str(e)}")
                return False
                
        elif platform == "ios":
            # Try newer iOS scrolling methods
            try:
                # Using the WebDriverAgent 'mobile:' scroll command
                predicate = f'name CONTAINS "{search_key}" OR label CONTAINS "{search_key}" OR value CONTAINS "{search_key}"'
                driver.execute_script('mobile: scroll', {
                    'predicateString': predicate,
                    'direction': 'down'
                })
                logger.debug(f"iOS scroll successful for {search_key}")
                return True
            except Exception as e:
                logger.debug(f"iOS scroll failed: {str(e)}")
                return False
                
        return False
        
    except Exception as e:
        logger.debug(f"Platform-specific scroll failed: {str(e)}")
        return False