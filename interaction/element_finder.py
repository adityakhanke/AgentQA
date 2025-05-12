"""
Element Finder: Enhanced element finder with multiple strategies and AI assistance.

This module provides advanced element finding capabilities with multiple
strategies, fallbacks, and AI-assisted correction of element locators.
"""

import asyncio
import difflib
import re
import time
from typing import List, Optional, Tuple

from appium.webdriver import WebElement
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.error_handler import handle_error
from tools.session_management import load_app
from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

class ElementFinder:
    """
    Enhanced element finder with multiple strategies and AI assistance.
    """
    
    def __init__(self):
        """Initialize the element finder."""
        self.platform = None
        self.driver = None
        
    async def setup(self, platform: str = "android") -> None:
        """
        Set up the element finder with a driver and platform.
        
        Args:
            platform: Target platform (android or ios)
        """
        self.platform = platform.lower()
        session = await load_app()
        if session.get("message") == "Success":
            self.driver = session["driver"]
        else:
            logger.error(f"Failed to initialize element finder: {session.get('error', 'Unknown error')}")
            
    async def find_element(
        self, 
        search_key: str, 
        timeout: float = 10.0,
        raise_exception: bool = False,
        use_ai_correction: bool = True
    ) -> Optional[WebElement]:
        """
        Find an element using multiple strategies.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            raise_exception: Whether to raise an exception if element not found
            use_ai_correction: Whether to use AI correction for missing elements
            
        Returns:
            WebElement if found, None otherwise
            
        Raises:
            NoSuchElementException: If element not found and raise_exception is True
        """
        if not self.driver:
            await self.setup()
            if not self.driver:
                logger.error("Driver not initialized, cannot find element")
                if raise_exception:
                    raise NoSuchElementException("Driver not initialized")
                return None
                
        logger.debug(f"Finding element with search key: {search_key}")
        
        # Define our search function for the wait utility
        async def search_with_strategies():
            # First try the faster, direct strategies
            element = await self._find_with_fast_strategies(search_key, timeout / 3)
            if element:
                return element
                
            # If not found, try more comprehensive strategies
            element = await self._find_with_comprehensive_strategies(search_key, timeout / 3)
            if element:
                return element
                
            # If still not found, try platform-specific strategies
            element = await self._find_with_platform_strategies(search_key, timeout / 3)
            if element:
                return element
                
            # If still not found and AI correction is requested, try AI correction
            if use_ai_correction:
                corrected_search_key = await self._get_ai_corrected_locator(search_key)
                if corrected_search_key and corrected_search_key != search_key:
                    logger.info(f"Trying AI-corrected locator: {corrected_search_key}")
                    
                    # Recursively try with the corrected key but without AI correction to avoid infinite loops
                    corrected_element = await self.find_element(
                        corrected_search_key, 
                        timeout=timeout / 2,
                        raise_exception=False,
                        use_ai_correction=False
                    )
                    if corrected_element:
                        return corrected_element
            
            return None
        
        # Use the wait utility to handle the timeout
        start_time = time.time()
        element = None
        
        try:
            # We need to run the async function in a synchronous context for WebDriverWait
            loop = asyncio.get_event_loop()
            
            # Keep trying until we find the element or timeout
            while time.time() - start_time < timeout:
                element = await search_with_strategies()
                if element:
                    return element
                # Small delay before trying again    
                await asyncio.sleep(0.2)
                
        except Exception as e:
            error_details = handle_error(e, f"Error finding element: {search_key}")
            logger.error(error_details["message"])
        
        # Element not found after all strategies
        if element is None and raise_exception:
            logger.error(f"Element not found with search key: {search_key}")
            raise NoSuchElementException(f"Element not found: {search_key}")
            
        return element
        
    async def wait_for_element(
        self, 
        search_key: str, 
        timeout: float = 20.0,
        until_condition: str = "presence",
        use_ai_correction: bool = True
    ) -> Optional[WebElement]:
        """
        Wait for an element with a specific condition.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            until_condition: Condition to wait for (presence, visibility, clickable)
            use_ai_correction: Whether to use AI correction for missing elements
            
        Returns:
            WebElement if found, None otherwise
        """
        if not self.driver:
            await self.setup()
            if not self.driver:
                logger.error("Driver not initialized, cannot wait for element")
                return None
        
        # Define the condition check function
        async def check_condition():
            element = await self.find_element(
                search_key,
                timeout=1.0,  # Short timeout for each attempt
                use_ai_correction=use_ai_correction
            )
            
            if not element:
                return None
                
            try:
                if until_condition.lower() == "presence":
                    return element
                elif until_condition.lower() == "visibility":
                    return element if element.is_displayed() else None
                elif until_condition.lower() == "clickable":
                    return element if element.is_displayed() and element.is_enabled() else None
                elif until_condition.lower() == "invisible":
                    return True if not element.is_displayed() else None
                else:
                    return element
            except (StaleElementReferenceException, WebDriverException):
                return None
        
        # Use wait utility
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            result = await check_condition()
            if result:
                return result
            await asyncio.sleep(0.2)
        
        logger.warning(f"Timed out waiting for element: {search_key} (condition: {until_condition})")
        return None
        
    async def find_elements(
        self, 
        search_key: str, 
        timeout: float = 10.0
    ) -> List[WebElement]:
        """
        Find all elements matching the search key.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the elements
            
        Returns:
            List of matching WebElements
        """
        if not self.driver:
            await self.setup()
            if not self.driver:
                logger.error("Driver not initialized, cannot find elements")
                return []
                
        logger.debug(f"Finding elements with search key: {search_key}")
        
        locator_strategies = self._get_prioritized_locator_strategies(search_key)
        all_elements = []
        
        # Keep track of time to respect the overall timeout
        start_time = time.time()
        
        for locator_type, locator_value in locator_strategies:
            # Check if we've exceeded the timeout
            if time.time() - start_time >= timeout:
                break
                
            try:
                # Distribute remaining time among strategies
                remaining_time = timeout - (time.time() - start_time)
                per_strategy_timeout = remaining_time / max(1, len(locator_strategies))
                
                # Use a short wait to find elements with this strategy
                wait = WebDriverWait(self.driver, min(per_strategy_timeout, 2.0))
                elements = wait.until(
                    lambda d: d.find_elements(locator_type, locator_value)
                )
                
                if elements:
                    all_elements.extend(elements)
            except (TimeoutException, StaleElementReferenceException, WebDriverException):
                pass
        
        # Filter out duplicates (same element might be found by different strategies)
        # This is an approximation based on element location and size
        unique_elements = []
        element_signatures = set()
        
        for element in all_elements:
            try:
                # Create a signature based on location and size
                location = element.location
                size = element.size
                signature = (
                    round(location['x']), 
                    round(location['y']),
                    round(size['width']), 
                    round(size['height'])
                )
                
                if signature not in element_signatures:
                    element_signatures.add(signature)
                    unique_elements.append(element)
            except (StaleElementReferenceException, WebDriverException):
                # Skip stale elements
                pass
        
        logger.debug(f"Found {len(unique_elements)} unique elements matching: {search_key}")
        return unique_elements
        
    async def element_exists(self, search_key: str, timeout: float = 5.0) -> bool:
        """
        Check if an element exists.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            
        Returns:
            True if the element exists, False otherwise
        """
        element = await self.find_element(search_key, timeout, raise_exception=False)
        return element is not None
        
    async def is_element_visible(self, search_key: str, timeout: float = 5.0) -> bool:
        """
        Check if an element is visible.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            
        Returns:
            True if the element is visible, False otherwise
        """
        element = await self.find_element(search_key, timeout, raise_exception=False)
        if not element:
            return False
            
        try:
            return element.is_displayed()
        except Exception:
            return False
            
    async def get_text(self, search_key: str, timeout: float = 10.0) -> Optional[str]:
        """
        Get text from an element.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            
        Returns:
            Text from the element or None if not found
        """
        element = await self.find_element(search_key, timeout, raise_exception=False)
        if not element:
            return None
            
        try:
            text = element.text
            if not text and self.platform == "android":
                text = element.get_attribute("text") or ""
            elif not text and self.platform == "ios":
                text = element.get_attribute("label") or element.get_attribute("value") or ""
                
            return text
        except Exception as e:
            logger.warning(f"Failed to get text from element: {str(e)}")
            return None
    
    async def _find_with_fast_strategies(self, search_key: str, timeout: float) -> Optional[WebElement]:
        """
        Find an element using fast, direct strategies.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            
        Returns:
            WebElement if found, None otherwise
        """
        # Try ID strategies first (fastest)
        strategies = [
            (By.ID, search_key),                                   # Exact resource ID
            (By.ACCESSIBILITY_ID, search_key),                     # Accessibility ID/Content Desc
            (By.XPATH, f"//*[@resource-id='{search_key}']"),      # Resource ID via XPath
        ]
        
        start_time = time.time()
        per_strategy_timeout = timeout / len(strategies)
        
        for locator_type, locator_value in strategies:
            # Check if we've exceeded the timeout
            if time.time() - start_time >= timeout:
                break
                
            try:
                # Use a short wait for each strategy
                wait = WebDriverWait(self.driver, min(per_strategy_timeout, 2.0))
                element = wait.until(
                    EC.presence_of_element_located((locator_type, locator_value))
                )
                logger.debug(f"Found element with fast strategy: {locator_type}, {locator_value}")
                return element
            except (TimeoutException, StaleElementReferenceException, WebDriverException):
                pass
                
        return None
    
    async def _find_with_comprehensive_strategies(self, search_key: str, timeout: float) -> Optional[WebElement]:
        """
        Find an element using more comprehensive strategies.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            
        Returns:
            WebElement if found, None otherwise
        """
        # More thorough strategies
        strategies = [
            # Text-based strategies
            (By.XPATH, f"//*[contains(@text, '{search_key}')]"),              # Text contains
            (By.XPATH, f"//*[normalize-space(@text) = '{search_key}']"),      # Text exact match
            
            # Resource ID partial match
            (By.XPATH, f"//*[contains(@resource-id, '{search_key}')]"),       # Resource ID contains
            
            # Content description / accessibility label
            (By.XPATH, f"//*[contains(@content-desc, '{search_key}')]"),      # Content-desc contains
            
            # Class-based with text
            (By.XPATH, f"//android.widget.Button[contains(@text, '{search_key}')]"),  # Android button
            (By.XPATH, f"//android.widget.TextView[contains(@text, '{search_key}')]"), # Android text
            
            # Name attribute (iOS)
            (By.XPATH, f"//*[contains(@name, '{search_key}')]"),              # Name contains
            
            # Value attribute (iOS)
            (By.XPATH, f"//*[contains(@value, '{search_key}')]"),             # Value contains
            
            # Label attribute (iOS)
            (By.XPATH, f"//*[contains(@label, '{search_key}')]"),             # Label contains
        ]
        
        start_time = time.time()
        per_strategy_timeout = timeout / len(strategies)
        
        for locator_type, locator_value in strategies:
            # Check if we've exceeded the timeout
            if time.time() - start_time >= timeout:
                break
                
            try:
                # Use a short wait for each strategy
                wait = WebDriverWait(self.driver, min(per_strategy_timeout, 1.0))
                element = wait.until(
                    EC.presence_of_element_located((locator_type, locator_value))
                )
                logger.debug(f"Found element with comprehensive strategy: {locator_type}, {locator_value}")
                return element
            except (TimeoutException, StaleElementReferenceException, WebDriverException):
                pass
                
        return None
    
    async def _find_with_platform_strategies(self, search_key: str, timeout: float) -> Optional[WebElement]:
        """
        Find an element using platform-specific strategies.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            
        Returns:
            WebElement if found, None otherwise
        """
        if self.platform == "android":
            return await self._find_with_android_strategies(search_key, timeout)
        elif self.platform == "ios":
            return await self._find_with_ios_strategies(search_key, timeout)
        return None
    
    async def _find_with_android_strategies(self, search_key: str, timeout: float) -> Optional[WebElement]:
        """
        Find an element using Android-specific strategies.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            
        Returns:
            WebElement if found, None otherwise
        """
        # UiAutomator strategies
        selectors = [
            f"new UiSelector().text(\"{search_key}\")",                                 # Exact text match
            f"new UiSelector().textContains(\"{search_key}\")",                         # Text contains
            f"new UiSelector().resourceId(\"{search_key}\")",                           # Exact resource ID
            f"new UiSelector().description(\"{search_key}\")",                          # Exact content-desc
            f"new UiSelector().descriptionContains(\"{search_key}\")",                  # Content-desc contains
            f"new UiSelector().className(\"android.widget.Button\").text(\"{search_key}\")",  # Button with text
            f"new UiSelector().className(\"android.widget.EditText\").text(\"{search_key}\")",  # EditText with text
            f"new UiSelector().className(\"android.widget.TextView\").text(\"{search_key}\")",  # TextView with text
            
            # Advanced selectors for complex UI
            f"new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().textContains(\"{search_key}\"))",  # Scroll to text
        ]
        
        start_time = time.time()
        per_selector_timeout = timeout / len(selectors)
        
        for selector in selectors:
            # Check if we've exceeded the timeout
            if time.time() - start_time >= timeout:
                break
                
            try:
                # Use a shorter wait for each selector
                wait = WebDriverWait(self.driver, min(per_selector_timeout, 1.0))
                element = wait.until(
                    lambda d: d.find_element(AppiumBy.ANDROID_UIAUTOMATOR, selector)
                )
                logger.debug(f"Found element with Android strategy: {selector}")
                return element
            except (TimeoutException, StaleElementReferenceException, WebDriverException):
                pass
                
        return None
    
    async def _find_with_ios_strategies(self, search_key: str, timeout: float) -> Optional[WebElement]:
        """
        Find an element using iOS-specific strategies.
        
        Args:
            search_key: The search key (ID, text, etc.)
            timeout: Maximum time to wait for the element
            
        Returns:
            WebElement if found, None otherwise
        """
        # iOS predicates
        predicates = [
            f"label == '{search_key}'",                       # Exact label match
            f"name == '{search_key}'",                        # Exact name match
            f"value == '{search_key}'",                       # Exact value match
            f"label CONTAINS '{search_key}'",                 # Label contains
            f"name CONTAINS '{search_key}'",                  # Name contains
            f"value CONTAINS '{search_key}'",                 # Value contains
            f"type == 'XCUIElementTypeButton' AND label CONTAINS '{search_key}'",  # Button with label
            f"type == 'XCUIElementTypeTextField' AND label CONTAINS '{search_key}'",  # TextField with label
            f"type == 'XCUIElementTypeStaticText' AND label CONTAINS '{search_key}'",  # StaticText with label
        ]
        
        # Class chains
        chains = [
            f"**/XCUIElementTypeAny[`label == '{search_key}'`]",              # Any element with label
            f"**/XCUIElementTypeAny[`name == '{search_key}'`]",               # Any element with name
            f"**/XCUIElementTypeButton[`label CONTAINS '{search_key}'`]",     # Button containing label
            f"**/XCUIElementTypeStaticText[`label CONTAINS '{search_key}'`]", # Text containing label
        ]
        
        start_time = time.time()
        total_strategies = len(predicates) + len(chains)
        per_strategy_timeout = timeout / total_strategies
        
        # Try predicates first
        for predicate in predicates:
            # Check if we've exceeded the timeout
            if time.time() - start_time >= timeout:
                break
                
            try:
                wait = WebDriverWait(self.driver, min(per_strategy_timeout, 1.0))
                element = wait.until(
                    lambda d: d.find_element(AppiumBy.IOS_PREDICATE, predicate)
                )
                logger.debug(f"Found element with iOS predicate: {predicate}")
                return element
            except (TimeoutException, StaleElementReferenceException, WebDriverException):
                pass
                
        # Then try class chains
        for chain in chains:
            # Check if we've exceeded the timeout
            if time.time() - start_time >= timeout:
                break
                
            try:
                wait = WebDriverWait(self.driver, min(per_strategy_timeout, 1.0))
                element = wait.until(
                    lambda d: d.find_element(AppiumBy.IOS_CLASS_CHAIN, chain)
                )
                logger.debug(f"Found element with iOS class chain: {chain}")
                return element
            except (TimeoutException, StaleElementReferenceException, WebDriverException):
                pass
                
        return None
    
    async def _get_ai_corrected_locator(self, search_key: str) -> Optional[str]:
        """
        Use AI to suggest a corrected locator when element not found.
        
        Args:
            search_key: The original search key that failed
            
        Returns:
            Corrected search key or None if not available
        """
        # This would integrate with a Checker Agent, but for now we'll use a simple fallback
        # Get page source
        try:
            if not self.driver:
                return None
                
            page_source = self.driver.page_source
            
            # Simple string similarity check (could be replaced with AI model)
            if self.platform == "android":
                # Look for similar resource IDs
                pattern = r'resource-id="([^"]*)"'
                resource_ids = re.findall(pattern, page_source)
                
                for resource_id in resource_ids:
                    if search_key.lower() in resource_id.lower() or self._string_similarity(search_key, resource_id) > 0.7:
                        logger.info(f"Found similar resource ID: {resource_id}")
                        return resource_id
                        
                # Look for similar text
                pattern = r'text="([^"]*)"'
                texts = re.findall(pattern, page_source)
                
                for text in texts:
                    if search_key.lower() in text.lower() or self._string_similarity(search_key, text) > 0.7:
                        logger.info(f"Found similar text: {text}")
                        return text
                        
            elif self.platform == "ios":
                # Look for similar names or labels
                pattern = r'name="([^"]*)"'
                names = re.findall(pattern, page_source)
                
                for name in names:
                    if search_key.lower() in name.lower() or self._string_similarity(search_key, name) > 0.7:
                        logger.info(f"Found similar name: {name}")
                        return name
                        
                pattern = r'label="([^"]*)"'
                labels = re.findall(pattern, page_source)
                
                for label in labels:
                    if search_key.lower() in label.lower() or self._string_similarity(search_key, label) > 0.7:
                        logger.info(f"Found similar label: {label}")
                        return label
        
        except Exception as e:
            logger.warning(f"Error in AI correction: {str(e)}")
            
        return None
    
    def _get_prioritized_locator_strategies(self, search_key: str) -> List[Tuple[str, str]]:
        """
        Get a prioritized list of locator strategies for the given search key.
        
        Args:
            search_key: The search key
            
        Returns:
            List of tuples containing (locator_type, locator_value)
        """
        strategies = []
        
        # Add direct strategies
        strategies.extend([
            (By.ID, search_key),
            (By.ACCESSIBILITY_ID, search_key),
            (By.XPATH, f"//*[@resource-id='{search_key}']"),
        ])
        
        # Add text-based strategies
        strategies.extend([
            (By.XPATH, f"//*[contains(@text, '{search_key}')]"),
            (By.XPATH, f"//*[normalize-space(@text) = '{search_key}']"),
        ])
        
        # Add platform-specific strategies
        if self.platform == "android":
            strategies.extend([
                (By.XPATH, f"//*[contains(@content-desc, '{search_key}')]"),
                (AppiumBy.ANDROID_UIAUTOMATOR, f"new UiSelector().text(\"{search_key}\")"),
                (AppiumBy.ANDROID_UIAUTOMATOR, f"new UiSelector().textContains(\"{search_key}\")"),
                (AppiumBy.ANDROID_UIAUTOMATOR, f"new UiSelector().resourceId(\"{search_key}\")"),
                (AppiumBy.ANDROID_UIAUTOMATOR, f"new UiSelector().descriptionContains(\"{search_key}\")"),
            ])
        elif self.platform == "ios":
            strategies.extend([
                (By.XPATH, f"//*[contains(@name, '{search_key}')]"),
                (By.XPATH, f"//*[contains(@label, '{search_key}')]"),
                (By.XPATH, f"//*[contains(@value, '{search_key}')]"),
                (AppiumBy.IOS_PREDICATE, f"label CONTAINS '{search_key}'"),
                (AppiumBy.IOS_PREDICATE, f"name CONTAINS '{search_key}'"),
                (AppiumBy.IOS_CLASS_CHAIN, f"**/XCUIElementTypeAny[`label CONTAINS '{search_key}'`]"),
            ])
        
        return strategies
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate string similarity ratio between two strings.
        
        Args:
            s1: First string
            s2: Second string
            
        Returns:
            Similarity ratio between 0 and 1
        """
        return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

# Create a singleton instance
element_finder = ElementFinder()

async def find_element(
    search_key: str, 
    timeout: float = 10.0, 
    raise_exception: bool = False
) -> Optional[WebElement]:
    """
    Convenient global function to find an element.
    
    Args:
        search_key: The search key
        timeout: Timeout in seconds
        raise_exception: Whether to raise an exception if not found
        
    Returns:
        WebElement if found, None otherwise
    """
    return await element_finder.find_element(search_key, timeout, raise_exception)

async def wait_for_visible(search_key: str, timeout: float = 10.0) -> Optional[WebElement]:
    """
    Wait for an element to be visible.
    
    Args:
        search_key: The search key
        timeout: Timeout in seconds
        
    Returns:
        WebElement if visible, None otherwise
    """
    return await element_finder.wait_for_element(
        search_key, 
        timeout=timeout, 
        until_condition="visibility"
    )

async def element_exists(search_key: str, timeout: float = 5.0) -> bool:
    """
    Check if an element exists.
    
    Args:
        search_key: The search key
        timeout: Timeout in seconds
        
    Returns:
        True if exists, False otherwise
    """
    return await element_finder.element_exists(search_key, timeout)