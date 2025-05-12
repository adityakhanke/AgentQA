"""
Session Management: Manages Appium sessions for mobile testing.

This module provides tools for creating, managing, and cleaning up Appium
sessions for mobile test automation.
"""

import asyncio
import os
from typing import Dict, Any

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from selenium.common.exceptions import WebDriverException

from core.error_handler import handle_error
from tools.tool_registry import tool
from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

# Global driver instance
driver = None

@tool(
    agent_names=["executor"],
    description="Initialize or get the existing Appium session using configuration from context manager",
    name="load_app",
    parameters={},
    output={
        "type": Dict[str, Any],
        "description": "Dictionary containing driver instance and status information"
    }
)
async def load_app() -> Dict[str, Any]:
    """
    Initialize or get the existing Appium session using configuration from context manager.
    
    Returns:
        Dictionary containing driver instance and status information
    """
    global driver
    
    # If driver already exists, return it
    if driver is not None:
        logger.debug("Returning existing Appium session")
        return {"message": "Success", "driver": driver}
    
    # Start new session
    try:
        # Load configuration from context manager
        from core.context_manager import ContextManager

        config = ContextManager.get("config", {})
        platform = ContextManager.get("platform", "android").lower()
        reset_session = ContextManager.get("reset_session", False)
        
        # If reset is requested, quit any existing driver
        if reset_session and driver:
            await quit_driver()
            
        logger.info(f"Initializing new Appium session for {platform}")
        
        # Appium server URL from config or environment or default
        appium_server_url = config.get("appium", {}).get("server_url")
        if not appium_server_url:
            appium_server_url = os.environ.get('APPIUM_SERVER_URL', 'http://localhost:4723')
        
        # Get platform-specific options
        if platform == "android":
            options = _get_android_options(config)
        elif platform == "ios":
            options = _get_ios_options(config)
        else:
            return {"message": "Failure", "error": f"Unsupported platform: {platform}"}
        
        # Initialize the driver
        logger.info(f"Connecting to Appium server at: {appium_server_url}")
        driver = webdriver.Remote(appium_server_url, options=options)
        
        # Wait for app to initialize
        await asyncio.sleep(2)
        
        logger.info(f"Appium session initialized with ID: {driver.session_id}")
        return {"message": "Success", "driver": driver}
        
    except Exception as e:
        error_details = handle_error(e, "Failed to initialize Appium session")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor"],
    description="Quit the current Appium session",
    name="quit_app",
    parameters={},
    output={
        "type": Dict[str, Any],
        "description": "Status of the quit operation"
    }
)
async def quit_driver() -> Dict[str, Any]:
    """
    Quit the current Appium session.
    
    Returns:
        Status of the quit operation
    """
    global driver
    
    if driver is None:
        logger.warning("No active Appium session to quit")
        return {"message": "Success", "details": "No active session"}
    
    try:
        logger.info(f"Quitting Appium session: {driver.session_id}")
        driver.quit()
        driver = None
        return {"message": "Success", "details": "Session terminated"}
        
    except Exception as e:
        error_details = handle_error(e, "Failed to quit Appium session")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

@tool(
    agent_names=["executor", "checker"],
    description="Restart the current Appium session",
    name="restart_app",
    parameters={},
    output={
        "type": Dict[str, Any],
        "description": "Status of the restart operation and new driver instance"
    }
)
async def restart_app() -> Dict[str, Any]:
    """
    Restart the current Appium session.
    
    Returns:
        Status of the restart operation and new driver instance
    """
    await quit_driver()
    return await load_app()

@tool(
    agent_names=["executor", "checker"],
    description="Get the page source of the current screen",
    name="page_source",
    parameters={},
    output={
        "type": Dict[str, Any],
        "description": "Page source of the current screen"
    }
)
async def page_source() -> Dict[str, Any]:
    """
    Get the page source of the current screen.
    
    Returns:
        Page source of the current screen
    """
    try:
        session = await load_app()
        if session.get("message") != "Success":
            return session
        
        driver = session["driver"]
        return {"message": "Success", "body": driver.page_source}
        
    except Exception as e:
        error_details = handle_error(e, "Failed to get page source")
        logger.error(error_details["message"])
        return {"message": "Failure", "error": error_details["message"]}

def _get_android_options(config: Dict[str, Any]) -> UiAutomator2Options:
    """
    Get Android-specific options for Appium from config.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        UiAutomator2Options instance
    """
    # Get Android configuration from config
    android_config = config.get("appium").get("android")

    # Create capabilities dictionary
    capabilities = {
        "platformName": "Android",
        "automationName": android_config.get("automation_name", "UiAutomator2"),
        "deviceName": android_config.get("device_name", "Android"),
        "language": "en",
        "locale": "US"
    }
    
    # Add app package and activity
    app_package = android_config.get("app_package")
    app_activity = android_config.get("app_activity")
    
    if app_package:
        capabilities["appPackage"] = app_package
        
    if app_activity:
        capabilities["appActivity"] = app_activity
    
    # Add platform version if provided
    platform_version = android_config.get("platform_version")
    if platform_version:
        capabilities["platformVersion"] = platform_version

    # Add app path if provided
    app_path = android_config.get("app")
    if app_path:
        capabilities["app"] = app_path
    
    # Additional capabilities
    if android_config.get("no_reset") is not None:
        capabilities["noReset"] = android_config.get("no_reset")
    
    if android_config.get("full_reset") is not None:
        capabilities["fullReset"] = android_config.get("full_reset")
    
    if android_config.get("new_command_timeout") is not None:
        capabilities["newCommandTimeout"] = android_config.get("new_command_timeout")
    
    if android_config.get("auto_grant_permissions") is not None:
        capabilities["autoGrantPermissions"] = android_config.get("auto_grant_permissions")
    
    # Create options object with capabilities
    options = UiAutomator2Options()
    options.load_capabilities(capabilities)
    
    logger.info(f"Android capabilities: {capabilities}")
    return options

def _get_ios_options(config: Dict[str, Any]) -> XCUITestOptions:
    """
    Get iOS-specific options for Appium from config.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        XCUITestOptions instance
    """
    # Get iOS configuration from config
    ios_config = config.get("appium", {}).get("ios", {})
    
    # Create capabilities dictionary
    capabilities = {
        "platformName": "iOS",
        "automationName": ios_config.get("automation_name", "XCUITest"),
        "deviceName": ios_config.get("device_name", "iPhone Simulator"),
        "language": "en",
        "locale": "US"
    }
    
    # Add bundle ID
    bundle_id = ios_config.get("bundle_id")
    if bundle_id:
        capabilities["bundleId"] = bundle_id
    else:
        # Default to Preferences app if no bundle ID specified
        capabilities["bundleId"] = "com.apple.Preferences"
    
    # Add platform version if provided
    platform_version = ios_config.get("platform_version")
    if platform_version:
        capabilities["platformVersion"] = platform_version
    
    # Add app path if provided
    app_path = ios_config.get("app")
    if app_path:
        capabilities["app"] = app_path
    
    # Additional capabilities
    if ios_config.get("no_reset") is not None:
        capabilities["noReset"] = ios_config.get("no_reset")

    if ios_config.get("full_reset") is not None:
        capabilities["fullReset"] = ios_config.get("full_reset")
    
    if ios_config.get("new_command_timeout") is not None:
        capabilities["newCommandTimeout"] = ios_config.get("new_command_timeout")
    
    # iOS-specific capabilities
    if ios_config.get("use_new_wda") is not None:
        capabilities["useNewWDA"] = ios_config.get("use_new_wda")
    
    wda_local_port = ios_config.get("wda_local_port")
    if wda_local_port:
        capabilities["wdaLocalPort"] = int(wda_local_port)
    
    if ios_config.get("auto_accept_alerts") is not None:
        capabilities["autoAcceptAlerts"] = ios_config.get("auto_accept_alerts")
    
    # Create options object with capabilities
    options = XCUITestOptions()
    options.load_capabilities(capabilities)
    
    logger.info(f"iOS capabilities: {capabilities}")
    return options