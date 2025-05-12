"""
Screenshot Manager: Handles capturing and managing screenshots during test execution.
"""

import base64
import datetime
import logging
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

class ScreenshotManager:
    """
    Handles capturing and managing screenshots during test execution.
    """
    
    def __init__(
        self, 
        driver,
        screenshot_dir: str = "screenshots",
        max_screenshots: int = 100,
        include_timestamp: bool = True
    ):
        """
        Initialize the screenshot manager.
        
        Args:
            driver: The WebDriver instance
            screenshot_dir: Directory to store screenshots
            max_screenshots: Maximum number of screenshots to keep
            include_timestamp: Whether to include timestamp in filenames
        """
        self.driver = driver
        self.screenshot_dir = Path(screenshot_dir)
        self.max_screenshots = max_screenshots
        self.include_timestamp = include_timestamp
        self.screenshots = []
        
        # Create the screenshot directory if it doesn't exist
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"Initialized ScreenshotManager with directory: {screenshot_dir}")
        
    def take_screenshot(
        self, 
        name: Optional[str] = None,
        element = None,
        save_to_disk: bool = True
    ) -> Optional[str]:
        """
        Take a screenshot of the current screen or a specific element.
        
        Args:
            name: Optional name for the screenshot
            element: Optional element to screenshot (if None, captures full screen)
            save_to_disk: Whether to save the screenshot to disk
            
        Returns:
            Path to the saved screenshot or None if failed
        """
        if not self.driver:
            logger.warning("No WebDriver available for taking screenshots")
            return None
        
        try:
            # Generate a filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            
            if name:
                # Sanitize the name to make it safe for filesystem
                safe_name = self._sanitize_filename(name)
                filename = f"{timestamp}_{safe_name}.png" if self.include_timestamp else f"{safe_name}.png"
            else:
                filename = f"{timestamp}.png" if self.include_timestamp else "screenshot.png"
                
            filepath = self.screenshot_dir / filename
            
            # Take the screenshot
            if element:
                # Element screenshot
                try:
                    success = element.screenshot(str(filepath))
                    screenshot_type = "element"
                except:
                    # Fall back to full screen if element screenshot fails
                    success = self.driver.save_screenshot(str(filepath))
                    screenshot_type = "fallback"
            else:
                # Full screen screenshot
                success = self.driver.save_screenshot(str(filepath))
                screenshot_type = "screen"
                
            if success:
                logger.debug(f"Saved {screenshot_type} screenshot to: {filepath}")
                
                # Keep track of the screenshot
                screenshot_info = {
                    "path": str(filepath),
                    "name": name,
                    "type": screenshot_type,
                    "timestamp": timestamp
                }
                self.screenshots.append(screenshot_info)
                
                # Enforce the maximum number of screenshots
                self._enforce_max_screenshots()
                
                return str(filepath)
            else:
                logger.warning(f"Failed to save screenshot to: {filepath}")
                return None
                
        except Exception as e:
            logger.warning(f"Error taking screenshot: {str(e)}")
            return None
            
    def take_element_screenshot(
        self, 
        element, 
        name: Optional[str] = None
    ) -> Optional[str]:
        """
        Take a screenshot of a specific element.
        
        Args:
            element: The element to screenshot
            name: Optional name for the screenshot
            
        Returns:
            Path to the saved screenshot or None if failed
        """
        return self.take_screenshot(name=name, element=element)
        
    def get_latest_screenshot(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest screenshot information.
        
        Returns:
            Dictionary with screenshot information or None if no screenshots
        """
        if not self.screenshots:
            return None
            
        return self.screenshots[-1]
        
    def get_screenshots(self) -> List[Dict[str, Any]]:
        """
        Get all screenshot information.
        
        Returns:
            List of dictionaries with screenshot information
        """
        return self.screenshots
        
    def clear_screenshots(self, older_than_seconds: Optional[float] = None) -> int:
        """
        Clear screenshots.
        
        Args:
            older_than_seconds: Only clear screenshots older than this many seconds
            
        Returns:
            Number of screenshots cleared
        """
        if older_than_seconds is not None:
            # Clear screenshots older than the specified time
            current_time = time.time()
            threshold_time = current_time - older_than_seconds
            
            cleared_count = 0
            remaining_screenshots = []
            
            for screenshot in self.screenshots:
                filepath = screenshot["path"]
                file_path = Path(filepath)
                
                if file_path.exists():
                    file_mtime = file_path.stat().st_mtime
                    
                    if file_mtime < threshold_time:
                        try:
                            file_path.unlink()
                            cleared_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to delete screenshot: {filepath} - {str(e)}")
                            remaining_screenshots.append(screenshot)
                    else:
                        remaining_screenshots.append(screenshot)
                else:
                    # File doesn't exist, don't include in remaining screenshots
                    cleared_count += 1
                    
            self.screenshots = remaining_screenshots
            return cleared_count
        else:
            # Clear all screenshots
            cleared_count = 0
            
            for screenshot in self.screenshots:
                filepath = screenshot["path"]
                file_path = Path(filepath)
                
                if file_path.exists():
                    try:
                        file_path.unlink()
                        cleared_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete screenshot: {filepath} - {str(e)}")
                        
            self.screenshots = []
            return cleared_count
            
    def get_screenshot_as_base64(self) -> Optional[str]:
        """
        Get the current screen as a base64 encoded string.
        
        Returns:
            Base64 encoded screenshot or None if failed
        """
        if not self.driver:
            return None
            
        try:
            screenshot = self.driver.get_screenshot_as_base64()
            return screenshot
        except Exception as e:
            logger.warning(f"Failed to get screenshot as base64: {str(e)}")
            return None
            
    def _enforce_max_screenshots(self) -> None:
        """
        Enforce the maximum number of screenshots by deleting the oldest ones.
        """
        if len(self.screenshots) <= self.max_screenshots:
            return
            
        # Calculate how many screenshots to delete
        delete_count = len(self.screenshots) - self.max_screenshots
        
        # Get the oldest screenshots to delete
        screenshots_to_delete = self.screenshots[:delete_count]
        
        # Delete the files
        for screenshot in screenshots_to_delete:
            filepath = screenshot["path"]
            file_path = Path(filepath)
            
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete old screenshot: {filepath} - {str(e)}")
                    
        # Update the screenshots list
        self.screenshots = self.screenshots[delete_count:]
        
    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a name to be safe for use in a filename.
        
        Args:
            name: The name to sanitize
            
        Returns:
            A sanitized version of the name
        """
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = name
        
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
            
        # Limit length to avoid filesystem issues
        if len(sanitized) > 50:
            sanitized = sanitized[:47] + '...'
            
        return sanitized
        
    def create_test_report_with_screenshots(
        self, 
        test_name: str,
        test_result: Dict[str, Any],
        output_dir: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a test report HTML with embedded screenshots.
        
        Args:
            test_name: Name of the test
            test_result: Test result data
            output_dir: Directory to save the report (defaults to screenshot_dir)
            
        Returns:
            Path to the generated report or None if failed
        """
        if not output_dir:
            output_dir = self.screenshot_dir
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
        try:
            # Generate a report filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self._sanitize_filename(test_name)
            report_filename = f"{timestamp}_{safe_name}_report.html"
            report_path = output_dir / report_filename
            
            # Start building the HTML report
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Test Report: {test_name}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .header {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; }}
                    .pass {{ color: green; }}
                    .fail {{ color: red; }}
                    .error {{ color: orange; }}
                    .step {{ margin: 10px 0; border-left: 3px solid #ccc; padding-left: 10px; }}
                    .step.pass {{ border-left-color: green; }}
                    .step.fail {{ border-left-color: red; }}
                    .step.error {{ border-left-color: orange; }}
                    .screenshot {{ margin: 10px 0; }}
                    .screenshot img {{ max-width: 100%; max-height: 400px; border: 1px solid #ddd; }}
                    pre {{ background-color: #f9f9f9; padding: 10px; overflow-x: auto; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Test Report: {test_name}</h1>
                    <p>Timestamp: {timestamp}</p>
                    <p>Status: <span class="{test_result.get('status', 'unknown').lower()}">{test_result.get('status', 'Unknown')}</span></p>
                </div>
                
                <h2>Test Steps</h2>
            """
            
            # Add steps
            steps = test_result.get("steps", [])
            for step in steps:
                step_status = step.get("status", "unknown").lower()
                step_desc = step.get("description", "Unknown step")
                step_message = step.get("message", "")
                step_error = step.get("error", "")
                
                html += f"""
                <div class="step {step_status}">
                    <h3>{step_desc}</h3>
                    <p>Status: <span class="{step_status}">{step_status.upper()}</span></p>
                """
                
                if step_message:
                    html += f"<p>Message: {step_message}</p>"
                    
                if step_error:
                    html += f"""
                    <div class="error-details">
                        <p>Error: {step_error}</p>
                    </div>
                    """
                    
                # Add step screenshot if available
                step_screenshot = step.get("screenshot")
                if step_screenshot:
                    screenshot_path = Path(step_screenshot)
                    if screenshot_path.exists():
                        # Get relative path to make links work in the HTML
                        rel_path = os.path.relpath(step_screenshot, start=output_dir)
                        
                        html += f"""
                        <div class="screenshot">
                            <h4>Screenshot:</h4>
                            <a href="{rel_path}" target="_blank">
                                <img src="{rel_path}" alt="Step Screenshot">
                            </a>
                        </div>
                        """
                        
                html += "</div>"
                
            # Add summary screenshots section if there are any
            if self.screenshots:
                html += """
                <h2>All Screenshots</h2>
                <div class="screenshots-gallery">
                """
                
                for screenshot in self.screenshots:
                    filepath = screenshot.get("path")
                    name = screenshot.get("name", "Unnamed")
                    timestamp = screenshot.get("timestamp", "")
                    
                    screenshot_path = Path(filepath)
                    if screenshot_path.exists():
                        # Get relative path
                        rel_path = os.path.relpath(filepath, start=output_dir)
                        
                        html += f"""
                        <div class="screenshot">
                            <h4>{name} ({timestamp})</h4>
                            <a href="{rel_path}" target="_blank">
                                <img src="{rel_path}" alt="{name}">
                            </a>
                        </div>
                        """
                        
                html += "</div>"
                
            # Close the HTML
            html += """
            </body>
            </html>
            """
            
            # Write the report
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html)
                
            logger.info(f"Generated test report: {report_path}")
            return str(report_path)
            
        except Exception as e:
            logger.warning(f"Failed to create test report: {str(e)}")
            return None