from gherkin.parser import GherkinParser
from typing import Dict, Any
from utils.logger import get_logger
import re

# Configure logger
logger = get_logger(__name__)

class InterruptHandlerParser:
    """Parser for Gherkin-format interrupt handlers."""
    
    def __init__(self):
        self.gherkin_parser = GherkinParser()
        
    def parse_handler_file(self, file_path: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse a file containing interrupt handler definitions.
        
        Args:
            file_path: Path to the handler file
            
        Returns:
            Dictionary mapping handler names to handler definitions
        """
        try:
            # Read and parse the file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            return self.parse_handlers(content)
            
        except Exception as e:
            logger.error(f"Failed to parse interrupt handler file: {str(e)}")
            return {}
    
    def parse_handlers(self, content: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse Gherkin content for interrupt handlers.
        
        Args:
            content: Gherkin content with handler definitions
            
        Returns:
            Dictionary mapping handler names to handler definitions
        """
        handlers = {}
        
        # Parse the Gherkin content
        parsed = self.gherkin_parser.parse(content)
        
        # Check if this is a handler feature
        feature_tags = parsed.get("tags", [])
        if "@InterruptHandler" not in feature_tags:
            return handlers
            
        # Process each scenario as a potential handler
        for scenario in parsed.get("scenarios", []):
            scenario_tags = scenario.get("tags", [])
            
            # Find handler tag
            handler_name = None
            for tag in scenario_tags:
                if tag.startswith("@Handler:"):
                    handler_name = tag[9:]  # Remove the "@Handler:" prefix
                    break
                    
            if not handler_name:
                continue
                
            # Extract detection and action elements from steps
            detection_elements = []
            action_elements = []
            
            for step in scenario.get("steps", []):
                step_text = step.get("text", "")
                
                # Parse detection elements
                if "I see element" in step_text:
                    match = re.search(r'I see element "([^"]+)"', step_text)
                    if match:
                        detection_elements.append(match.group(1))
                
                # Parse action elements
                if "I tap on" in step_text:
                    match = re.search(r'I tap on "([^"]+)"', step_text)
                    if match:
                        action_elements.append({
                            "type": "tap",
                            "element": match.group(1)
                        })
                elif "I wait for" in step_text:
                    match = re.search(r'I wait for (\d+)', step_text)
                    if match:
                        action_elements.append({
                            "type": "wait",
                            "duration": int(match.group(1))
                        })
                elif "I enter" in step_text and "in" in step_text:
                    match = re.search(r'I enter "([^"]+)" in "([^"]+)"', step_text)
                    if match:
                        text = match.group(1)
                        element = match.group(2)
                        action_elements.append({
                            "type": "custom_tool",
                            "tool_name": "send_keys",
                            "args": [element, text]
                        })
            
            # Create handler definition
            handlers[handler_name] = {
                "name": scenario.get("name", handler_name),
                "detection_elements": detection_elements,
                "action_elements": action_elements
            }
            
        return handlers