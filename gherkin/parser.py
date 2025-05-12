"""
Gherkin Parser: Parses Gherkin feature files into structured JSON.

This module provides a parser for Gherkin feature files, converting them
into a structured JSON format that can be processed by the Parser Agent.
"""

import re
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Iterator, Union

from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

class GherkinParser:
    """
    Parse Gherkin feature files into structured JSON format.
    """
    
    def __init__(self):
        """Initialize the Gherkin parser."""
        # Regular expressions for Gherkin syntax
        self.feature_pattern = re.compile(r'Feature:(.+)$', re.MULTILINE)
        self.scenario_pattern = re.compile(r'(Scenario:|Scenario Outline:)(.+)$', re.MULTILINE)
        self.background_pattern = re.compile(r'Background:(.*)$', re.MULTILINE)
        self.step_pattern = re.compile(r'(Given|When|Then|And|But)\s+(.+)$', re.MULTILINE)
        self.examples_pattern = re.compile(r'Examples:(.*?)(?=(?:\n\s*(?:Scenario|Feature|$)))', re.DOTALL)
        self.tag_pattern = re.compile(r'(@\w+)(?:\s+|$)')
        self.comment_pattern = re.compile(r'#.*$', re.MULTILINE)
        self.docstring_pattern = re.compile(r'"""(.*?)"""', re.DOTALL)
        self.table_pattern = re.compile(r'(\s*\|.+\|.*)(?:\n\s*\|.+\|.*)*', re.MULTILINE)
        
    def parse_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse a Gherkin feature file into structured JSON.
        
        Args:
            file_path: Path to the feature file
            
        Returns:
            Dictionary containing parsed feature data
        """
        try:
            # Read the feature file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Parse the content
            result = self.parse(content)
            
            # Add file information
            result['file'] = str(file_path)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to parse feature file '{file_path}': {str(e)}")
            return {
                "error": f"Failed to parse feature file: {str(e)}",
                "file": str(file_path)
            }
    
    def parse(self, content: str) -> Dict[str, Any]:
        """
        Parse Gherkin content into structured JSON.
        
        Args:
            content: Gherkin content to parse
            
        Returns:
            Dictionary containing parsed feature data
        """
        try:
            # Remove comments
            content = self._remove_comments(content)
            
            # Extract feature information
            feature_info = self._extract_feature(content)
            
            # Extract scenarios
            scenarios = self._extract_scenarios(content)
            
            # Extract background if present
            background = self._extract_background(content)
            
            # Build the result
            result = {
                "feature": feature_info["name"],
                "description": feature_info["description"],
                "tags": feature_info["tags"],
                "scenarios": scenarios
            }
            
            # Add background if present
            if background:
                result["background"] = background
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to parse Gherkin content: {str(e)}")
            return {
                "error": f"Failed to parse Gherkin content: {str(e)}"
            }
            
    def parse_for_agent(self, content: str) -> Dict[str, Any]:
        """
        Parse Gherkin content into a format specifically for Parser Agent.
        
        Args:
            content: Gherkin content to parse
            
        Returns:
            Dictionary containing parsed feature data in Parser Agent format
        """
        try:
            # Parse the content
            parsed = self.parse(content)
            
            # Format for Parser Agent
            # For simplicity, we'll assume the first scenario
            if "scenarios" in parsed and parsed["scenarios"]:
                scenario = parsed["scenarios"][0]
                
                result = {
                    "feature": {
                        "name": parsed.get("feature", "Unknown Feature"),
                        "description": parsed.get("description", "")
                    },
                    "scenario": {
                        "name": scenario.get("name", "Unknown Scenario"),
                        "description": scenario.get("description", "")
                    },
                    "steps": []
                }
                
                # Convert steps to the expected format
                for step in scenario.get("steps", []):
                    step_data = {
                        "step_type": step.get("keyword", "Given"),
                        "description": step.get("text", ""),
                        "action": self._infer_action(step.get("text", "")),
                        "element": self._extract_element(step.get("text", "")),
                        "test_data": self._extract_test_data(step.get("text", ""), step.get("data", {}))
                    }
                    
                    # Add expected result for 'Then' steps
                    if step.get("keyword", "").strip() == "Then":
                        step_data["expected_result"] = self._extract_expected_result(step.get("text", ""))
                        
                    result["steps"].append(step_data)
                    
                return result
            else:
                return {
                    "error": "No scenarios found in Gherkin content",
                    "feature": {
                        "name": parsed.get("feature", "Unknown Feature"),
                        "description": parsed.get("description", "")
                    },
                    "scenario": {
                        "name": "Unknown Scenario",
                        "description": ""
                    },
                    "steps": []
                }
                
        except Exception as e:
            logger.error(f"Failed to parse Gherkin content for agent: {str(e)}")
            return {
                "error": f"Failed to parse Gherkin content for agent: {str(e)}",
                "feature": {
                    "name": "Error in Feature",
                    "description": str(e)
                },
                "scenario": {
                    "name": "Error in Scenario",
                    "description": ""
                },
                "steps": []
            }
    
    def _remove_comments(self, content: str) -> str:
        """
        Remove comments from Gherkin content.
        
        Args:
            content: Gherkin content
            
        Returns:
            Content with comments removed
        """
        return re.sub(self.comment_pattern, '', content)
    
    def _extract_feature(self, content: str) -> Dict[str, Any]:
        """
        Extract feature information from Gherkin content.
        
        Args:
            content: Gherkin content
            
        Returns:
            Dictionary containing feature name, description, and tags
        """
        # Find feature match
        feature_match = re.search(self.feature_pattern, content)
        if not feature_match:
            return {
                "name": "Unknown Feature",
                "description": "",
                "tags": []
            }
            
        # Extract feature name
        feature_name = feature_match.group(1).strip()
        
        # Find the position of the feature definition
        feature_pos = feature_match.start()
        
        # Extract tags before the feature
        tags_content = content[:feature_pos]
        tags = self._extract_tags(tags_content)
        
        # Extract description
        # Description is text between feature definition and first scenario or background
        next_section_pattern = re.compile(r'(Scenario:|Background:)', re.MULTILINE)
        next_section_match = re.search(next_section_pattern, content[feature_pos:])
        
        if next_section_match:
            description_end = feature_pos + next_section_match.start()
            description_content = content[feature_pos + len(feature_match.group(0)):description_end]
        else:
            description_content = content[feature_pos + len(feature_match.group(0)):]
            
        # Clean up description
        description = description_content.strip()
        
        return {
            "name": feature_name,
            "description": description,
            "tags": tags
        }
    
    def _extract_scenarios(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract scenarios from Gherkin content.
        
        Args:
            content: Gherkin content
            
        Returns:
            List of dictionaries containing scenario information
        """
        scenarios = []
        
        # Find all scenario matches
        scenario_matches = list(re.finditer(self.scenario_pattern, content))
        
        for i, scenario_match in enumerate(scenario_matches):
            # Extract scenario name
            scenario_type = scenario_match.group(1).strip()
            scenario_name = scenario_match.group(2).strip()
            
            # Determine if this is a scenario outline
            is_outline = scenario_type == "Scenario Outline:"
            
            # Find the position of the scenario definition
            scenario_pos = scenario_match.start()
            
            # Determine the end position (next scenario or end of content)
            if i < len(scenario_matches) - 1:
                scenario_end = scenario_matches[i + 1].start()
            else:
                scenario_end = len(content)
                
            # Extract the scenario content
            scenario_content = content[scenario_pos:scenario_end]
            
            # Extract tags before the scenario
            tags_section_end = scenario_match.start()
            tags_section_start = scenario_pos
            
            # Look for the previous scenario or feature to determine the start of tags
            if i > 0:
                tags_section_start = scenario_matches[i - 1].end()
            else:
                # If this is the first scenario, look for feature
                feature_match = re.search(self.feature_pattern, content)
                if feature_match:
                    tags_section_start = feature_match.end()
            
            tags_content = content[tags_section_start:tags_section_end]
            tags = self._extract_tags(tags_content)
            
            # Extract steps
            steps = self._extract_steps(scenario_content)
            
            # Extract examples for scenario outlines
            examples = []
            if is_outline:
                examples = self._extract_examples(scenario_content)
                
            # Build the scenario object
            scenario = {
                "name": scenario_name,
                "type": "outline" if is_outline else "scenario",
                "tags": tags,
                "steps": steps
            }
            
            if is_outline and examples:
                scenario["examples"] = examples
                
            scenarios.append(scenario)
            
        return scenarios
    
    def _extract_background(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Extract background from Gherkin content.
        
        Args:
            content: Gherkin content
            
        Returns:
            Dictionary containing background information or None if not present
        """
        # Find background match
        background_match = re.search(self.background_pattern, content)
        if not background_match:
            return None
            
        # Find the position of the background definition
        background_pos = background_match.start()
        
        # Determine the end position (next scenario or end of content)
        scenario_match = re.search(self.scenario_pattern, content[background_pos:])
        
        if scenario_match:
            background_end = background_pos + scenario_match.start()
        else:
            background_end = len(content)
            
        # Extract the background content
        background_content = content[background_pos:background_end]
        
        # Extract steps
        steps = self._extract_steps(background_content)
        
        return {
            "steps": steps
        }
    
    def _extract_steps(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract steps from Gherkin content.
        
        Args:
            content: Gherkin content
            
        Returns:
            List of dictionaries containing step information
        """
        steps = []
        
        # Find all step matches
        step_matches = list(re.finditer(self.step_pattern, content))
        
        for i, step_match in enumerate(step_matches):
            # Extract step keyword and text
            step_keyword = step_match.group(1).strip()
            step_text = step_match.group(2).strip()
            
            # Find the position of the step definition
            step_pos = step_match.start()
            
            # Determine the end position (next step, examples, or end of content)
            if i < len(step_matches) - 1:
                step_end = step_matches[i + 1].start()
            else:
                # Check for examples
                examples_match = re.search(self.examples_pattern, content[step_pos:])
                if examples_match:
                    step_end = step_pos + examples_match.start()
                else:
                    step_end = len(content)
                    
            # Extract the step content
            step_content = content[step_pos:step_end]
            
            # Extract docstring if present
            docstring = None
            docstring_match = re.search(self.docstring_pattern, step_content)
            if docstring_match:
                docstring = docstring_match.group(1).strip()
                
            # Extract table if present
            data_table = None
            table_match = re.search(self.table_pattern, step_content)
            if table_match:
                table_str = table_match.group(0)
                data_table = self._parse_table(table_str)
                
            # Build the step object
            step = {
                "keyword": step_keyword,
                "text": step_text
            }
            
            if docstring:
                step["docstring"] = docstring
                
            if data_table:
                step["data"] = data_table
                
            steps.append(step)
            
        return steps
    
    def _extract_examples(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract examples from scenario outline content.
        
        Args:
            content: Scenario outline content
            
        Returns:
            List of dictionaries containing example data
        """
        examples = []
        
        # Find all examples matches
        examples_matches = list(re.finditer(self.examples_pattern, content))
        
        for examples_match in examples_matches:
            examples_content = examples_match.group(1).strip()
            
            # Extract table
            table_match = re.search(self.table_pattern, examples_content)
            if not table_match:
                continue
                
            table_str = table_match.group(0)
            data_table = self._parse_table(table_str)
            
            # Extract tags
            tags_content = examples_content[:table_match.start()]
            tags = self._extract_tags(tags_content)
            
            examples.append({
                "tags": tags,
                "data": data_table
            })
            
        return examples
    
    def _parse_table(self, table_str: str) -> Dict[str, Any]:
        """
        Parse a Gherkin table into a structured format.
        
        Args:
            table_str: Table string
            
        Returns:
            Dictionary containing table data
        """
        lines = table_str.strip().split('\n')
        
        # Extract header and data rows
        if not lines:
            return {'headers': [], 'rows': []}
            
        # Parse header
        header_line = lines[0].strip()
        headers = [cell.strip() for cell in header_line.split('|') if cell.strip()]
        
        # Parse data rows
        rows = []
        for i in range(1, len(lines)):
            row_line = lines[i].strip()
            if not row_line:
                continue
                
            row_cells = [cell.strip() for cell in row_line.split('|') if cell.strip()]
            
            # Create a dictionary for the row
            row = {}
            for j, header in enumerate(headers):
                if j < len(row_cells):
                    row[header] = row_cells[j]
                else:
                    row[header] = ""
                    
            rows.append(row)
            
        return {
            'headers': headers,
            'rows': rows
        }
    
    def _extract_tags(self, content: str) -> List[str]:
        """
        Extract tags from Gherkin content.
        
        Args:
            content: Gherkin content
            
        Returns:
            List of tags
        """
        # Find all tag matches
        tag_matches = re.findall(self.tag_pattern, content)
        
        # Extract and clean tags
        tags = [tag.strip() for tag in tag_matches if tag.strip()]
        
        return tags
    
    def _infer_action(self, step_text: str) -> str:
        """
        Infer the action from a step text for Parser Agent format.
        
        Args:
            step_text: Step text
            
        Returns:
            Inferred action type
        """
        step_lower = step_text.lower()
        
        if any(x in step_lower for x in ["open", "launch", "navigate", "go to", "visit"]):
            return "navigate"
        elif any(x in step_lower for x in ["click", "tap", "press", "touch", "select button"]):
            return "tap"
        elif any(x in step_lower for x in ["type", "enter", "input", "fill", "write"]):
            return "input_text"
        elif any(x in step_lower for x in ["select from dropdown", "choose option", "select option"]):
            return "select_option"
        elif any(x in step_lower for x in ["should see", "should display", "verify", "check", "assert", "confirm"]):
            return "verify"
        elif any(x in step_lower for x in ["swipe", "scroll"]):
            return "swipe"
        elif any(x in step_lower for x in ["wait", "pause"]):
            return "wait"
        else:
            # Default to the most likely action based on step type
            if step_lower.startswith("given "):
                return "navigate"
            elif step_lower.startswith("when "):
                return "tap"
            elif step_lower.startswith("then "):
                return "verify"
            else:
                return "tap"  # Most common action
    
    def _extract_element(self, step_text: str) -> str:
        """
        Extract the UI element from a step text for Parser Agent format.
        
        Args:
            step_text: Step text
            
        Returns:
            Extracted element identifier
        """
        # Look for quoted text which often indicates element names
        quoted_match = re.search(r'"([^"]+)"', step_text)
        if quoted_match:
            return quoted_match.group(1)
            
        # Look for words following common action verbs
        element_patterns = [
            r'(?:click|tap|press) (?:on|the) (.+?)(?:button|link|icon|element)?(?:\s|$)',
            r'(?:enter|input|type) .+ (?:in|into) (?:the) (.+?)(?:field|input|textbox)?(?:\s|$)',
            r'(?:select) .+ (?:from) (?:the) (.+?)(?:dropdown|list|menu)?(?:\s|$)',
            r'(?:see|verify|check) (?:the) (.+?)(?:is|should|appears|displayed)?(?:\s|$)'
        ]
        
        for pattern in element_patterns:
            match = re.search(pattern, step_text.lower())
            if match:
                return match.group(1).strip()
                
        # If no specific pattern matched, use some heuristics
        words = step_text.split()
        for i, word in enumerate(words):
            if word.lower() in ["button", "field", "input", "dropdown", "screen", "page"]:
                if i > 0:
                    return words[i-1].strip()
        
        # Fall back to a generic element name
        return "element"
    
    def _extract_test_data(self, step_text: str, data_table: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract test data from a step text for Parser Agent format.
        
        Args:
            step_text: Step text
            data_table: Data table if present
            
        Returns:
            Extracted test data
        """
        test_data = {}
        
        # Look for quoted text which often indicates input values
        quoted_matches = re.findall(r'"([^"]+)"', step_text)
        if len(quoted_matches) >= 2:
            # If we have at least two quoted strings, assume first is field, second is value
            test_data[quoted_matches[0]] = quoted_matches[1]
        elif len(quoted_matches) == 1:
            # If we have just one quoted string, try to infer the field
            value = quoted_matches[0]
            
            # Look for words that indicate credentials
            if any(x in step_text.lower() for x in ["username", "login", "email", "user"]):
                test_data["username"] = value
            elif any(x in step_text.lower() for x in ["password", "pass"]):
                test_data["password"] = value
            elif any(x in step_text.lower() for x in ["name"]):
                test_data["name"] = value
            else:
                # Default to a generic value key
                test_data["value"] = value
        
        # If we have a data table, use it
        if data_table and 'rows' in data_table and data_table['rows']:
            # Take the first row for simplicity
            test_data.update(data_table['rows'][0])
            
        return test_data
    
    def _extract_expected_result(self, step_text: str) -> str:
        """
        Extract expected result from a 'Then' step for Parser Agent format.
        
        Args:
            step_text: Step text
            
        Returns:
            Extracted expected result
        """
        # For verification steps, the expected result is often the element or text to verify
        lower_text = step_text.lower()
        
        if "see" in lower_text or "display" in lower_text:
            # Look for quoted text which often indicates expected text
            quoted_match = re.search(r'"([^"]+)"', step_text)
            if quoted_match:
                return quoted_match.group(1) + "_displayed"
                
        # Look for specific verification words
        verify_patterns = [
            r'(?:see|verify|check) (?:the|that|if) (.+?)(?:is|should be|appears|displayed)?(?:\s|$)',
            r'(?:should|must|will) (?:see|display|show) (.+?)(?:\s|$)'
        ]
        
        for pattern in verify_patterns:
            match = re.search(pattern, lower_text)
            if match:
                element = match.group(1).strip()
                return element + "_displayed"
                
        # Handle special cases
        if "enabled" in lower_text:
            return "element_enabled"
        elif "disabled" in lower_text:
            return "element_disabled"
        elif "selected" in lower_text:
            return "element_selected"
        elif "contains" in lower_text:
            return "element_contains_text"
        elif "not" in lower_text:
            return "element_not_displayed"
            
        # Default expected result
        return "element_displayed"