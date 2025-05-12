# screen_registry.py
from pathlib import Path
from typing import Dict, List, Optional, Any
from gherkin.parser import GherkinParser
from tools.tool_registry import get_tool_function

class ScreenRegistry:
    """Manages screen definitions and provides validation capabilities."""
    
    def __init__(self, screens_dir: str = "screens"):
        self.screens_dir = Path(screens_dir)
        self.parser = GherkinParser()
        self.screens = {}
        self._load_screen_definitions()
        
    async def _load_screen_definitions(self) -> None:
        """Load all screen definitions from the screens directory."""
        if not self.screens_dir.exists():
            return
            
        for screen_file in self.screens_dir.glob("*.feature"):
            try:
                with open(screen_file, 'r') as f:
                    screen_content = f.read()

                parsed_screen = self.parser.parse(screen_content)
                # Only process files with @Screen tag
                if parsed_screen.get("tags") and "@Screen" in parsed_screen.get("tags"):
                    screen_name = parsed_screen.get("feature")
                    self.screens[screen_name] = await self._process_screen_definition(parsed_screen)
            except Exception as e:
                print(f"Error loading screen definition {screen_file}: {e}")

    def _extract_elements(self, scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract element definitions from a scenario."""
        elements = []
        for step in scenario.get("steps", []):
            text = step.get("text", "")
            
            # Pattern matching for different element types
            if "has heading" in text:
                elements.append({
                    "type": "heading",
                    "content": self._extract_quoted_text(text),
                    "description": text
                })
            elif "has input field" in text:
                elements.append({
                    "type": "input",
                    "hint": self._extract_quoted_text(text),
                    "description": text
                })
            elif "has button" in text:
                elements.append({
                    "type": "button",
                    "content": self._extract_quoted_text(text),
                    "description": text
                })
            elif "has link" in text:
                elements.append({
                    "type": "link",
                    "content": self._extract_quoted_text(text),
                    "description": text
                })
            elif "may have" in text:
                elements.append({
                    "type": "dynamic",
                    "description": text.replace("the screen may have ", "")
                })
            else:
                elements.append({
                    "type": "unknown",
                    "description": text
                })
                
        return elements
    
    def _extract_relationships(self, scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract layout relationships from a scenario."""
        relationships = []
        for step in scenario.get("steps", []):
            text = step.get("text", "")
            if "appears above" in text:
                elements = self._extract_quoted_texts(text)
                if len(elements) >= 2:
                    relationships.append({
                        "type": "above",
                        "upper": elements[0],
                        "lower": elements[1]
                    })
            elif "appears below" in text:
                elements = self._extract_quoted_texts(text)
                if len(elements) >= 2:
                    relationships.append({
                        "type": "below",
                        "lower": elements[0],
                        "upper": elements[1]
                    })
                    
        return relationships
    
    def _extract_transitions(self, scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract screen transitions from a scenario."""
        transitions = []
        for step in scenario.get("steps", []):
            text = step.get("text", "")
            if "navigates to" in text:
                elements = self._extract_quoted_texts(text)
                if len(elements) >= 2:
                    trigger = elements[0]
                    target = elements[1]
                    conditions = []
                    
                    # Check for conditions
                    if "with valid credentials" in text:
                        conditions.append("valid_credentials")
                    
                    transitions.append({
                        "trigger": trigger,
                        "target": target,
                        "conditions": conditions,
                        "description": text
                    })
                    
        return transitions
    
    def _extract_quoted_text(self, text: str) -> str:
        """Extract text inside the first pair of quotes."""
        import re
        match = re.search(r'"([^"]*)"', text)
        if match:
            return match.group(1)
        return ""
    
    def _extract_quoted_texts(self, text: str) -> List[str]:
        """Extract all quoted texts from a string."""
        import re
        return re.findall(r'"([^"]*)"', text)
    
    def get_screen(self, screen_name: str) -> Optional[Dict[str, Any]]:
        """Get a screen definition by name."""
        return self.screens.get(screen_name)
    
    def get_all_screens(self) -> Dict[str, Dict[str, Any]]:
        """Get all screen definitions."""
        return self.screens
    
    async def _process_screen_definition(self, parsed_screen: Dict[str, Any]) -> Dict[str, Any]:
        """Process a parsed screen definition into a simplified format."""
        screen_def = {
            "name": parsed_screen.get("feature", "Unknown Screen"),
            "description": parsed_screen.get("description", ""),
            "identifiers": []  # Only need identifiers now
        }

        # Process scenarios based on their tags
        for scenario in parsed_screen.get("scenarios", []):
            if "@Identity" in scenario.get("tags", []):
                screen_def["identifiers"] = self._extract_identifiers(scenario)
                
        return screen_def

    def _extract_identifiers(self, scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract screen identifiers from a scenario."""
        identifiers = []
        for step in scenario.get("steps", []):
            text = step.get("text", "")
            
            # Parse the identifier description
            if "shows" in text or "has" in text or "contains" in text:
                identifiers.append({
                    "description": text,
                    "content": self._extract_quoted_text(text) if '"' in text else text
                })
                
        return identifiers
    
    async def validate_current_screen(self, screen_name: str, page_source: str = None) -> Dict[str, Any]:
        """Simplified screen validation using only essential identifiers."""
        # Get screen definition
        screen_def = self.get_screen(screen_name)
        if not screen_def:
            return {"valid": False, "message": f"No definition found for screen: {screen_name}"}

        tool_func = get_tool_function("executor", "page_source")

        # Get page source if not provided
        if not page_source:
            page_source_result = await tool_func()
            page_source = page_source_result.get("body", "")
        
        # Check for identifiers - simplified matching
        identifiers = screen_def.get("identifiers", [])
        found_count = 0
        
        for identifier in identifiers:
            content = identifier.get("content", "")
            
            # Very simple check - if content is in page source
            if content and content in page_source:
                found_count += 1
            # For descriptive identifiers without quoted content
            elif not content and self._check_descriptive_identifier(identifier.get("description", ""), page_source):
                found_count += 1
        
        # Calculate match percentage
        total_identifiers = len(identifiers)
        match_score = found_count / total_identifiers if total_identifiers > 0 else 0
        
        return {
            "valid": match_score >= 0.5,  # Just need 50% of identifiers to match
            "match_score": match_score
        }