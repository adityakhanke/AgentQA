"""
Interactions: Input and UI interaction tools for mobile testing.

This module provides tools for various interactions like entering text,
clearing fields, selecting options, and more for mobile app testing.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple, Union

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
    description="Enter text into an input field",
    name="send_keys",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Input field identifier (ID, text, etc.)"
        },
        "text": {
            "type": "string",
            "description": "Text to enter"
        },
        "clear_first": {
            "type": "boolean",
            "description": "Whether to clear the field first",
            "default": True
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the text entry operation"
    }
)
async def send_keys(
    search_key: str,
    text: str,
    clear_first: bool = True
) -> Dict[str, Any]:
    """
    Enter text into an input field.
    
    Args:
        search_key: Input field identifier (ID, text, etc.)
        text: Text to enter
        clear_first: Whether to clear the field first
        
    Returns:
        Result of the text entry operation
    """
    logger.info(f"Entering text '{text}' into {search_key}")
    
    try:
        element = await find_element(search_key)
        if not element:
            return {"message": "Failure", "error": f"Input field not found: {search_key}"}
        
        if clear_first:
            element.clear()
            
        element.send_keys(text)
        
        return {
            "message": "Success",
            "details": f"Entered text '{text}' into {search_key}"
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to enter text into {search_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Clear text from an input field",
    name="clear_text",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Input field identifier (ID, text, etc.)"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the clear operation"
    }
)
async def clear_text(search_key: str) -> Dict[str, Any]:
    """
    Clear text from an input field.
    
    Args:
        search_key: Input field identifier (ID, text, etc.)
        
    Returns:
        Result of the clear operation
    """
    logger.info(f"Clearing text from {search_key}")
    
    try:
        element = await find_element(search_key)
        if not element:
            return {"message": "Failure", "error": f"Input field not found: {search_key}"}
        
        element.clear()
        
        return {
            "message": "Success",
            "details": f"Cleared text from {search_key}"
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to clear text from {search_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor", "checker"],
    description="Get text from an element",
    name="get_text",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier (ID, text, etc.)"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Element text content"
    }
)
async def get_text(search_key: str) -> Dict[str, Any]:
    """
    Get text from an element.
    
    Args:
        search_key: Element identifier (ID, text, etc.)
        
    Returns:
        Element text content
    """
    logger.info(f"Getting text from {search_key}")
    
    try:
        element = await find_element(search_key)
        if not element:
            return {"message": "Failure", "error": f"Element not found: {search_key}"}
        
        # Try different ways to get text based on platform
        text = await element_finder.get_text(search_key)
        if text is None:
            return {"message": "Failure", "error": f"Could not get text from {search_key}"}
        
        return {
            "message": "Success",
            "body": text
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to get text from {search_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor", "checker"],
    description="Check if an element is displayed",
    name="element_is_displayed",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier (ID, text, etc.)"
        },
        "timeout": {
            "type": "number",
            "description": "Maximum time to wait for the element in seconds",
            "default": 5.0
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result indicating if the element is displayed"
    }
)
async def element_is_displayed(
    search_key: str,
    timeout: float = 5.0
) -> Dict[str, Any]:
    """
    Check if an element is displayed.
    
    Args:
        search_key: Element identifier (ID, text, etc.)
        timeout: Maximum time to wait for the element in seconds
        
    Returns:
        Result indicating if the element is displayed
    """
    logger.info(f"Checking if {search_key} is displayed")
    
    try:
        is_visible = await element_finder.is_element_visible(search_key, timeout)
        
        return {
            "message": "Success",
            "body": is_visible
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to check if {search_key} is displayed")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor", "checker"],
    description="Check if an element is enabled",
    name="element_is_enabled",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier (ID, text, etc.)"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result indicating if the element is enabled"
    }
)
async def element_is_enabled(search_key: str) -> Dict[str, Any]:
    """
    Check if an element is enabled.
    
    Args:
        search_key: Element identifier (ID, text, etc.)
        
    Returns:
        Result indicating if the element is enabled
    """
    logger.info(f"Checking if {search_key} is enabled")
    
    try:
        element = await find_element(search_key)
        if not element:
            return {"message": "Failure", "error": f"Element not found: {search_key}"}
        
        is_enabled = element.is_enabled()
        
        return {
            "message": "Success",
            "body": is_enabled
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to check if {search_key} is enabled")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor", "checker"],
    description="Check if an element is selected",
    name="element_is_selected",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier (ID, text, etc.)"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result indicating if the element is selected"
    }
)
async def element_is_selected(search_key: str) -> Dict[str, Any]:
    """
    Check if an element is selected.
    
    Args:
        search_key: Element identifier (ID, text, etc.)
        
    Returns:
        Result indicating if the element is selected
    """
    logger.info(f"Checking if {search_key} is selected")
    
    try:
        element = await find_element(search_key)
        if not element:
            return {"message": "Failure", "error": f"Element not found: {search_key}"}
        
        is_selected = element.is_selected()
        
        return {
            "message": "Success",
            "body": is_selected
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to check if {search_key} is selected")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Select an option from a dropdown menu",
    name="select_option",
    parameters={
        "dropdown_key": {
            "type": "string",
            "description": "Dropdown element identifier (ID, text, etc.)"
        },
        "option_key": {
            "type": "string",
            "description": "Option to select (text, value, etc.)"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the select operation"
    }
)
async def select_option(
    dropdown_key: str,
    option_key: str
) -> Dict[str, Any]:
    """
    Select an option from a dropdown menu.
    
    Args:
        dropdown_key: Dropdown element identifier (ID, text, etc.)
        option_key: Option to select (text, value, etc.)
        
    Returns:
        Result of the select operation
    """
    logger.info(f"Selecting option '{option_key}' from dropdown {dropdown_key}")
    
    try:
        session = await load_app()
        if session.get("message") != "Success":
            return session
            
        # First click/tap on the dropdown to open it
        dropdown_tap_result = await single_tap(dropdown_key)
        if dropdown_tap_result.get("message") != "Success":
            return dropdown_tap_result
            
        # Wait for dropdown to open
        await asyncio.sleep(1)
        
        # Then click/tap on the option
        option_tap_result = await single_tap(option_key)
        if option_tap_result.get("message") != "Success":
            return option_tap_result
            
        return {
            "message": "Success",
            "details": f"Selected option '{option_key}' from dropdown {dropdown_key}"
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to select option '{option_key}' from dropdown {dropdown_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Get element attribute value",
    name="get_attribute",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier (ID, text, etc.)"
        },
        "attribute": {
            "type": "string",
            "description": "Attribute name to get"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Element attribute value"
    }
)
async def get_attribute(
    search_key: str,
    attribute: str
) -> Dict[str, Any]:
    """
    Get element attribute value.
    
    Args:
        search_key: Element identifier (ID, text, etc.)
        attribute: Attribute name to get
        
    Returns:
        Element attribute value
    """
    logger.info(f"Getting attribute '{attribute}' from {search_key}")
    
    try:
        element = await find_element(search_key)
        if not element:
            return {"message": "Failure", "error": f"Element not found: {search_key}"}
        
        value = element.get_attribute(attribute)
        
        return {
            "message": "Success",
            "body": value
        }
    except Exception as e:
        error_details = handle_error(e, f"Failed to get attribute '{attribute}' from {search_key}")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

# Import at the end to avoid circular imports
from tools.gestures import single_tap