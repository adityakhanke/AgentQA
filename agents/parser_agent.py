"""
Parser Agent: Parses Gherkin test cases into structured JSON.

This agent analyzes Gherkin feature specifications and converts them
into structured JSON format for the Implementor Agent to process.
Ensures all steps from the original Gherkin are properly mapped,
with enhanced support for screen definitions and network monitoring.
"""

import json
import re
from typing import Dict, Any, List, Optional

from agents.base_agent import BaseAgent
from core.context_manager import ContextManager
from core.error_handler import handle_error
from utils.logger import get_logger
from utils.extract_json import extract_json
from utils.network_monitor import NetworkMonitor

# Configure logger
logger = get_logger(__name__)

class ParserAgent(BaseAgent):
    """
    Agent responsible for parsing Gherkin test cases into structured JSON.
    Ensures all steps are properly mapped from the original Gherkin,
    with enhanced support for screen definitions and network monitoring.
    """
    
    def __init__(
        self,
        name: str,
        llm_config: Dict[str, Any],
        context_manager: ContextManager
    ):
        """
        Initialize the parser agent.
        
        Args:
            name: Agent name
            llm_config: LLM configuration
            context_manager: Context manager for shared state
        """
        super().__init__(name, llm_config, context_manager)
        
        # Initialize network monitor reference
        self.network_monitor = None
        driver = self.context_manager.get("driver")
        if driver:
            self.network_monitor = NetworkMonitor(driver)
            self.network_monitor.start_monitoring()
            self.context_manager.set("network_monitor", self.network_monitor)
            logger.info("Network monitoring initialized in Parser Agent")
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a Gherkin test case into structured JSON.
        
        Args:
            input_data: Input data containing the test case
                - test_case: The Gherkin test case to parse
                
        Returns:
            Dictionary containing the parsed test case
        """
        try:
            # Extract the test case from input data
            test_case = input_data.get("test_case")
            if not test_case:
                return {"error": "No test case provided"}
                
            # Pre-process the test case to count steps
            original_step_count = self._count_gherkin_steps(test_case)
            logger.info(f"Detected {original_step_count} steps in the original Gherkin test case")
            
            # Parse the test case
            parsed_test = await self._parse_test_case(test_case, original_step_count)
            
            # Return the parsed test case
            return parsed_test
            
        except Exception as e:
            error_details = handle_error(e, "Test parsing failed")
            logger.error(error_details["message"], exc_info=True)
            
            return {"error": error_details["message"]}
    
    def _count_gherkin_steps(self, test_case: str) -> int:
        """
        Count the number of steps in a Gherkin test case.
        
        Args:
            test_case: The Gherkin test case to count steps in
            
        Returns:
            The number of steps in the test case
        """
        # Regular expression to match Gherkin step keywords
        step_pattern = re.compile(r'^\s*(Given|When|Then|And|But)\s+', re.MULTILINE | re.IGNORECASE)
        steps = re.findall(step_pattern, test_case)
        
        return len(steps)
    
    async def _parse_test_case(self, test_case: str, expected_step_count: int) -> Dict[str, Any]:
        """
        Parse a Gherkin test case using LLM, ensuring all steps are captured.
        
        Args:
            test_case: The Gherkin test case to parse
            expected_step_count: The expected number of steps
            
        Returns:
            Parsed test case
        """
        try:
            # Create prompt for LLM
            prompt = self._create_parsing_prompt(test_case, expected_step_count)
            
            # Get LLM response
            llm_response = await self._get_llm_response(prompt)

            # Extract JSON from response
            parsed_test = extract_json(llm_response)

            if not parsed_test:
                # If no JSON found, try to parse the response as JSON directly
                try:
                    parsed_test = json.loads(llm_response)
                except json.JSONDecodeError:
                    logger.warning("Could not extract JSON from LLM response")
                    return {"error": "Could not parse test case"}
                    
            # Validate the parsed test and ensure all steps are captured
            if not self._validate_parsed_test(parsed_test, expected_step_count):
                logger.warning(f"Invalid parsed test structure or step count mismatch (expected {expected_step_count})")
                # Try one more time with a more explicit prompt
                retry_prompt = self._create_retry_prompt(test_case, expected_step_count, parsed_test)
                retry_response = await self._get_llm_response(retry_prompt)
                retry_parsed_test = extract_json(retry_response)
                
                if retry_parsed_test and self._validate_parsed_test(retry_parsed_test, expected_step_count):
                    parsed_test = retry_parsed_test
                else:
                    return {"error": f"Failed to parse all {expected_step_count} steps from the test case"}
                
            logger.info(f"Successfully parsed test case: {parsed_test.get('feature', {})}")

            # Enhance with screen context if available
            screens_registry = self.context_manager.get("screens_registry")
            if screens_registry:
                parsed_test = await self._enhance_with_screen_context(parsed_test, screens_registry)
                logger.info(f"Enhanced test case with screen contexts")

            # Add network monitoring information
            parsed_test = self._add_network_monitoring_context(parsed_test)
            
            return parsed_test
            
        except Exception as e:
            logger.error(f"Error parsing test case: {str(e)}")
            return {"error": f"Error parsing test case: {str(e)}"}
    
    async def _enhance_with_screen_context(self, parsed_test: Dict[str, Any], 
                                         screens_registry: Any) -> Dict[str, Any]:
        """
        Enhance parsed test with screen context information.
        
        Args:
            parsed_test: Parsed test data
            screens_registry: Registry of screen definitions
            
        Returns:
            Enhanced parsed test
        """
        # Extract screen references from steps
        screen_references = []
        
        # First, check feature and scenario for screen references
        feature_name = parsed_test.get("feature", "")
        if isinstance(feature_name, dict):
            feature_name = feature_name.get("name", "")
        
        scenario_name = parsed_test.get("scenario", "")
        if isinstance(scenario_name, dict):
            scenario_name = scenario_name.get("name", "")
            
        # Look for screen references in feature and scenario names
        all_screens = screens_registry.get_all_screens().keys()
        for screen_name in all_screens:
            if screen_name in feature_name or screen_name in scenario_name:
                screen_references.append({
                    "context": "feature/scenario",
                    "screen_name": screen_name
                })
            
        # Look for screen references in steps
        for step in parsed_test.get("steps", []):
            description = step.get("description", "")
            
            # Common patterns for screen references
            patterns = [
                r'(?:am on|navigate to|go to|should see) the ["\'](.+?)["\'] (?:screen|page)',
                r'(?:displays|shows|is on) the ["\'](.+?)["\'] (?:screen|page)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, description, re.IGNORECASE)
                for match in matches:
                    # Check if this matches a known screen
                    for screen_name in all_screens:
                        if match.lower() == screen_name.lower() or screen_name.lower() in match.lower():
                            screen_references.append({
                                "step": step,
                                "screen_name": screen_name
                            })
            
            # Also check for direct mentions of screens
            for screen_name in all_screens:
                if screen_name in description:
                    screen_references.append({
                        "step": step,
                        "screen_name": screen_name
                    })
        
        # Add screen contexts to the parsed test
        if screen_references:
            parsed_test["screen_contexts"] = []
            
            for ref in screen_references:
                screen_def = screens_registry.get_screen(ref["screen_name"])
                if screen_def:
                    screen_context = {
                        "screen_name": ref["screen_name"],
                        "identifiers": screen_def.get("identifiers", [])
                    }
                    
                    # Add step information if available
                    if "step" in ref:
                        screen_context["step_description"] = ref["step"]["description"]
                    
                    parsed_test["screen_contexts"].append(screen_context)
        
        return parsed_test
    
    def _add_network_monitoring_context(self, parsed_test: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add network monitoring context to parsed test.
        
        Args:
            parsed_test: Parsed test data
            
        Returns:
            Enhanced parsed test
        """
        # Add network monitoring flag to steps that likely need it
        steps = parsed_test.get("steps", [])
        enhanced_steps = []
        
        for step in steps:
            action = step.get("action", "").lower()
            description = step.get("description", "").lower()
            
            # Determine if this step likely triggers network activity
            triggers_network = False
            network_wait_timeout = 5  # Default timeout in seconds
            
            # Check for actions that typically trigger network activity
            if action in ["tap", "navigate", "swipe"]:
                triggers_network = True
            
            # Check for descriptions that likely trigger network activity
            network_trigger_terms = [
                "navigate", "go to", "open", "load", "refresh", "tap", "click", 
                "submit", "search", "login", "sign in", "register", "book", "order"
            ]
            
            for term in network_trigger_terms:
                if term in description:
                    triggers_network = True
                    break
            
            # Check for explicit wait instructions
            if "wait" in description:
                wait_match = re.search(r'wait (?:for|until)(?: network)?(?: is)? (?:idle|ready|loaded)(?:.+?(\d+) seconds)?', description, re.IGNORECASE)
                if wait_match:
                    triggers_network = True
                    if wait_match.group(1):
                        network_wait_timeout = int(wait_match.group(1))
            
            # Add network monitoring info to the step if needed
            if triggers_network:
                step["network_monitoring"] = {
                    "triggered": True,
                    "wait_timeout": network_wait_timeout
                }
            
            enhanced_steps.append(step)
        
        parsed_test["steps"] = enhanced_steps
        return parsed_test
    
    def _create_parsing_prompt(self, test_case: str, expected_step_count: int) -> str:
        """
        Create a prompt for the LLM to parse a test case, emphasizing step count.

        Args:
            test_case: The test case to parse
            expected_step_count: The expected number of steps

        Returns:
            Formatted prompt
        """
        # Define the example JSON as a separate string to avoid f-string escaping issues
        example_json = '''{
  "feature": "Login Feature",
  "scenario": "Successful Login",
  "steps": [
    {
      "step_type": "Given",
      "action": "navigate",
      "description": "User is on the login screen",
      "element": "login_screen"
    },
    {
      "step_type": "When",
      "action": "input_text",
      "description": "User enters valid credentials",
      "element": "username_field",
      "test_data": {
        "username": "testuser",
        "password": "password123"
      }
    },
    {
      "step_type": "And",
      "action": "tap",
      "description": "User taps the login button",
      "element": "login_button"
    },
    {
      "step_type": "Then",
      "action": "verify",
      "description": "User should be on the home screen",
      "element": "home_screen",
      "expected_result": "home_screen_displayed"
    }
  ]
}'''

        # Combine the parts using ordinary string formatting
        prompt = f"""
        You are an expert in test automation who converts Gherkin test cases into structured JSON.
        Your task is to parse the following Gherkin test case and extract its structure.

        # Gherkin Test Case
        ```gherkin
        {test_case}
        ```

        IMPORTANT: This Gherkin test case contains EXACTLY {expected_step_count} steps. Your JSON output MUST include ALL {expected_step_count} steps.
        
        Please convert this Gherkin test case into JSON with the following structure:
        - feature: The feature name
        - scenario: The scenario name
        - steps: An array of steps with these properties:
          - step_type: The step type (Given, When, Then, And)
          - action: The primary action (navigate, tap, input_text, etc.)
          - description: A clear description of the step
          - element: The UI element involved (if any)
          - test_data: Any test data involved (if any)
          - expected_result: Expected result for verification steps (if any)

        Use these action types:
        - navigate: For steps that navigate to a screen
        - tap: For tapping or clicking on elements
        - input_text: For entering text
        - select_option: For selecting from dropdowns
        - verify: For verification steps

        Remember:
        1. Your output MUST contain EXACTLY {expected_step_count} steps in the steps array.
        2. ANY 'And' or 'But' step should be treated as a SEPARATE step. For instance, in "Given x\\nAnd y", both "Given x" and "And y" are separate steps.
        3. Do not combine or omit any steps.
        4. "And" steps should take the action from context (e.g., after "When" steps, an "And" step would have an action type related to "When")

        Return only the structured JSON without any explanations.

        For example:
        ```json
        {example_json}
        ```
        """

        return prompt
        
    def _create_retry_prompt(self, test_case: str, expected_step_count: int, previous_attempt: Dict[str, Any]) -> str:
        """
        Create a retry prompt if the first attempt failed to parse all steps.
        
        Args:
            test_case: The test case to parse
            expected_step_count: The expected number of steps
            previous_attempt: The previous parsed result
            
        Returns:
            Formatted retry prompt
        """
        previous_step_count = len(previous_attempt.get("steps", []))
        
        prompt = f"""
        You are an expert in test automation who converts Gherkin test cases into structured JSON.
        
        A previous parsing attempt failed to capture all steps. The test case has {expected_step_count} steps, but only {previous_step_count} were parsed.
        
        # Gherkin Test Case
        ```gherkin
        {test_case}
        ```
        
        CRITICAL: You MUST extract EXACTLY {expected_step_count} steps. Each line starting with Given, When, Then, And, or But is a separate step.

        Previous attempt (INCOMPLETE with only {previous_step_count} steps):
        ```json
        {json.dumps(previous_attempt, indent=2)}
        ```
        
        Create a new JSON that includes ALL {expected_step_count} steps. Do not combine steps.
        
        Return only the complete JSON with all {expected_step_count} steps.
        """
        
        return prompt

    async def _get_llm_response(self, prompt: str) -> str:
        """
        Get response from the LLM.

        Args:
            prompt: Prompt for the LLM

        Returns:
            LLM response
        """
        try:
            # Use the agent's LLM to generate a response
            messages = [
                {"role": "system", "content": "You are an expert in test automation who converts Gherkin test cases into structured JSON."},
                {"role": "user", "content": prompt}
            ]

            response = await self.llm.generate_response(messages)
            return response.content

        except Exception as e:
            logger.warning(f"Error getting LLM response: {str(e)}")
            return ""
    
    def _validate_parsed_test(self, parsed_test: Dict[str, Any], expected_step_count: int) -> bool:
        """
        Validate the structure of a parsed test and ensure it has the expected number of steps.
        
        Args:
            parsed_test: The parsed test to validate
            expected_step_count: The expected number of steps
            
        Returns:
            True if valid, False otherwise
        """
        # Check required fields
        if not parsed_test.get("feature"):
            logger.warning("Missing 'feature' field in parsed test")
            return False
            
        if not parsed_test.get("scenario"):
            logger.warning("Missing 'scenario' field in parsed test")
            return False
            
        if not parsed_test.get("steps"):
            logger.warning("Missing 'steps' field in parsed test")
            return False
            
        # Check steps structure
        steps = parsed_test["steps"]
        if not isinstance(steps, list):
            logger.warning("Invalid 'steps' field in parsed test")
            return False
            
        # Check step count
        if len(steps) != expected_step_count:
            logger.warning(f"Step count mismatch: expected {expected_step_count}, got {len(steps)}")
            return False
            
        # Validate individual steps
        for i, step in enumerate(steps):
            if not step.get("step_type"):
                logger.warning(f"Missing 'step_type' field in step {i+1}")
                return False
                
            if not step.get("action"):
                logger.warning(f"Missing 'action' field in step {i+1}")
                return False
                
            if not step.get("description"):
                logger.warning(f"Missing 'description' field in step {i+1}")
                return False

        return True