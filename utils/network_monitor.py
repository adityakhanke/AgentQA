# utils/network_monitor.py

import asyncio
import time
import logging
from typing import Optional

from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

class NetworkMonitor:
    """
    Monitor network activity in mobile applications during testing.
    Implemented as a singleton to ensure only one instance exists.
    """
    
    # Singleton instance
    _instance = None
    
    @classmethod
    def get_instance(cls, driver=None):
        """
        Get or create the singleton instance.
        
        Args:
            driver: WebDriver instance for the application (required for first initialization)
            
        Returns:
            NetworkMonitor instance
        """
        if cls._instance is None:
            if driver is None:
                logger.warning("Driver is required for initial NetworkMonitor initialization")
                return None
            cls._instance = cls(driver)
            cls._instance.start_monitoring()
        elif driver is not None and cls._instance.driver is None:
            # Update the driver if it was previously None
            cls._instance.driver = driver
            cls._instance.start_monitoring()
        return cls._instance
    
    def __init__(self, driver=None):
        """
        Initialize the network monitor.
        Note: Use get_instance() instead of direct instantiation.
        
        Args:
            driver: WebDriver instance for the application
        """
        # Check if this is the first instantiation
        if NetworkMonitor._instance is not None:
            logger.warning("NetworkMonitor is a singleton. Use get_instance() instead.")
            return
            
        self.driver = driver
        self.requests_in_flight = 0
        self.last_request_time = 0
        self.is_monitoring = False
        self.request_log = []
        NetworkMonitor._instance = self
        
    def start_monitoring(self) -> bool:
        """
        Initialize network monitoring based on available capabilities.
        
        Returns:
            True if monitoring was successfully started, False otherwise
        """
        if not self.driver:
            logger.warning("No driver available for network monitoring")
            return False
            
        try:
            if hasattr(self.driver, 'execute_cdp_cmd'):  # WebView-based or Chrome-based
                self._setup_cdp_monitoring()
            else:
                self._setup_proxy_monitoring()
                
            self.is_monitoring = True
            logger.info("Network monitoring started")
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize network monitoring: {str(e)}")
            return False
    
    def _setup_cdp_monitoring(self) -> None:
        """Set up Chrome DevTools Protocol monitoring."""
        # Enable network domain
        self.driver.execute_cdp_cmd('Network.enable', {})
        
        # Set up event listeners
        self.driver.execute_script("""
        window.networkRequests = 0;
        
        // Track request started
        window.addEventListener('_networkRequestStarted', function() {
            window.networkRequests++;
        });
        
        // Track request completed
        window.addEventListener('_networkRequestCompleted', function() {
            window.networkRequests = Math.max(0, window.networkRequests - 1);
        });
        """)
    
    def _setup_proxy_monitoring(self) -> None:
        """Set up proxy-based monitoring for native apps."""
        # For truly native apps, we use a simpler heuristic approach
        # based on periodic UI change detection
        pass
    
    async def get_active_requests_count(self) -> int:
        """
        Get the current number of in-flight requests.
        
        Returns:
            Number of active network requests
        """
        if not self.is_monitoring:
            return 0
            
        try:
            if hasattr(self.driver, 'execute_script'):
                return self.driver.execute_script("return window.networkRequests || 0;")
            else:
                return self.requests_in_flight
        except Exception:
            return 0
    
    async def wait_for_network_idle(self, timeout=10, idle_threshold=0.5, max_in_flight=0) -> bool:
        """
        Wait for network to become idle.
        
        Args:
            timeout: Maximum time to wait in seconds
            idle_threshold: Time network must be idle in seconds
            max_in_flight: Maximum requests allowed to still consider network idle
            
        Returns:
            True if network becomes idle, False if timeout occurs
        """
        if not self.is_monitoring:
            logger.debug("Network monitoring not active, skipping wait")
            return True
            
        start_time = time.time()
        idle_start = None
        
        while time.time() - start_time < timeout:
            # Get current request count
            requests = await self.get_active_requests_count()
            
            # Check if we consider this idle
            if requests <= max_in_flight:
                # Start or continue idle period
                if idle_start is None:
                    idle_start = time.time()
                    
                # Check if we've been idle long enough
                if time.time() - idle_start >= idle_threshold:
                    logger.debug(f"Network idle detected after {time.time() - start_time:.2f}s")
                    return True
            else:
                # Reset idle start time if requests become active
                idle_start = None
                
            # Short sleep to prevent CPU spinning
            await asyncio.sleep(0.1)
            
        logger.warning(f"Network did not become idle within {timeout}s timeout")
        return False
    
    async def wait_for_essential_content(self, timeout=15) -> bool:
        """
        Wait for essential content to load by combining network and UI heuristics.
        This is more reliable than just waiting for network idle.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if content appears to be loaded, False otherwise
        """
        start_time = time.time()
        
        # Wait for initial network burst to settle
        initial_idle = await self.wait_for_network_idle(timeout=timeout/3, idle_threshold=0.3)
        
        # Then wait for key UI changes to stabilize
        ui_stable = await self._wait_for_ui_stability(timeout=timeout/3)
        
        # Final check for any remaining network activity
        final_idle = await self.wait_for_network_idle(timeout=timeout/3, idle_threshold=0.5)
        
        total_time = time.time() - start_time
        logger.debug(f"Content load check completed in {total_time:.2f}s: network1={initial_idle}, ui={ui_stable}, network2={final_idle}")
        
        # Consider loaded if either network is idle or UI is stable
        return initial_idle or ui_stable
    
    async def _wait_for_ui_stability(self, timeout=5, check_interval=0.3) -> bool:
        """
        Wait for UI to stop changing - a proxy for content loading completion.
        
        Args:
            timeout: Maximum time to wait in seconds
            check_interval: Time between UI checks in seconds
            
        Returns:
            True if UI has stabilized, False otherwise
        """
        start_time = time.time()
        last_page_source = None
        stable_since = None
        
        while time.time() - start_time < timeout:
            try:
                # Get current page source as a proxy for UI state
                current_source = self.driver.page_source
                source_hash = hash(current_source)
                
                if last_page_source == source_hash:
                    # UI hasn't changed
                    if stable_since is None:
                        stable_since = time.time()
                    
                    # If UI stable for 1 second, consider it loaded
                    if time.time() - stable_since >= 1.0:
                        return True
                else:
                    # UI changed, reset stability timer
                    stable_since = None
                    last_page_source = source_hash
                
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.debug(f"Error during UI stability check: {str(e)}")
                return False
                
        return False
    
    @classmethod
    def reset_instance(cls):
        """
        Reset the singleton instance.
        Useful for testing or when needing to re-initialize with a new driver.
        """
        cls._instance = None
        logger.debug("NetworkMonitor singleton instance has been reset")