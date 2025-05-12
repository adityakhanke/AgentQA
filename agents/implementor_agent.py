"""
Implementor Agent: Maps test steps to executable tool commands.

This agent takes structured test steps from the Parser Agent and maps them
to executable tool commands for the Executor Agent to run. It ensures that
all steps from the Parser Agent are properly mapped to executable commands,
maintaining step count integrity through the testing pipeline.
"""

import json
from typing import Dict, Any, List

from agents.base_agent import BaseAgent
from core.context_manager import ContextManager
from core.error_handler import handle_error
from tools.tool_registry import get_tools_metadata_by_agent_name
from utils.logger import get_logger
from utils.extract_json import extract_json

# Configure logger
logger = get_logger(__name__)

class ImplementorAgent(BaseAgent):
    """
    Agent responsible for mapping test steps to executable tool commands.
    """
    
    def __init__(
        self,
        name: str,
        llm_config: Dict[str, Any],
        context_manager: ContextManager
    ):
        """
        Initialize the implementor agent.
        
        Args:
            name: Agent name
            llm_config: LLM configuration
            context_manager: Context manager for shared state
        """
        super().__init__(name, llm_config, context_manager)
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map test steps to executable tool commands.
        
        Args:
            input_data: Input data containing the parsed test steps
                - parsed_test: The parsed test steps
                
        Returns:
            Dictionary containing the mapped test steps
        """
        try:
            # Extract the parsed test steps from input data
            parsed_test = input_data.get("parsed_test")
            if not parsed_test:
                return {"error": "No parsed test provided"}
                
            # Map the test steps to executable tool commands
            mapped_steps = await self._map_test_steps(parsed_test)
            
            # Return the mapped test steps
            return {"test_implementation": mapped_steps}
            
        except Exception as e:
            error_details = handle_error(e, "Test mapping failed")
            logger.error(error_details["message"], exc_info=True)
            
            return {"error": error_details["message"]}
    
    async def _map_test_steps(self, parsed_test: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Map test steps to executable tool commands, ensuring all steps are accounted for.
        
        Args:
            parsed_test: The parsed test steps
            
        Returns:
            List of mapped test steps
        """
        # Get available tools for the executor agent
        executor_tools = get_tools_metadata_by_agent_name("executor")
        
        # Extract the original steps from the parsed test
        original_steps = parsed_test.get("steps", [])
        original_step_count = len(original_steps)
        
        if original_step_count == 0:
            logger.warning("No steps found in parsed test")
            return []
        
        # Maximum number of attempts to get a complete mapping
        max_attempts = 3
        missing_or_invalid_steps = []
        parameter_mismatches = []
        
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Mapping attempt {attempt}/{max_attempts}")

                # Create prompt for LLM with specific feedback about previous failures
                prompt = self._create_mapping_prompt(
                    parsed_test,
                    executor_tools,
                    attempt,
                    missing_or_invalid_steps,
                    parameter_mismatches
                )

                # Get LLM response
                llm_response = await self._get_llm_response(prompt)

                # Extract JSON from response
                mapped_steps = extract_json(llm_response)

                if not mapped_steps:
                    # If no JSON found, try to parse the response as JSON directly
                    try:
                        mapped_steps = json.loads(llm_response)
                    except json.JSONDecodeError:
                        logger.warning(f"Could not extract JSON from LLM response (attempt {attempt})")
                        continue

                # Validate the mapped steps and get specific issues
                validation_result = self._validate_mapped_steps(mapped_steps, original_steps, executor_tools)

                if validation_result["valid"]:
                    logger.info(f"Successfully mapped {len(mapped_steps)} test steps")
                    return mapped_steps
                else:
                    # Collect issues for the next attempt
                    missing_or_invalid_steps = validation_result.get("missing_or_invalid_steps", [])
                    parameter_mismatches = validation_result.get("parameter_mismatches", [])

                    issues = []
                    if missing_or_invalid_steps:
                        issues.append(f"Missing/invalid steps: {missing_or_invalid_steps}")
                    if parameter_mismatches:
                        issues.append(f"Parameter mismatches: {parameter_mismatches}")

                    logger.warning(f"Invalid mapping (attempt {attempt}): {', '.join(issues)}")
                    continue

            except Exception as e:
                logger.error(f"Error in mapping attempt {attempt}: {str(e)}")

        # If we've exhausted all attempts and still don't have a valid mapping
        error_details = []
        if missing_or_invalid_steps:
            error_details.append(f"Missing/invalid steps: {missing_or_invalid_steps}")
        if parameter_mismatches:
            error_details.append(f"Parameter mismatches: {parameter_mismatches}")

        error_msg = f"Failed to map all {original_step_count} steps after {max_attempts} attempts. Issues: {'; '.join(error_details)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # def _create_mapping_prompt(
    #     self,
    #     parsed_test: Dict[str, Any],
    #     executor_tools: List[Dict[str, Any]],
    #     attempt: int = 1,
    #     missing_or_invalid_steps: List[int] = None,
    #     parameter_mismatches: List[Dict[str, Any]] = None
    # ) -> str:
    #     """
    #     Create a prompt for the LLM to map test steps to tool commands.

    #     Args:
    #         parsed_test: The parsed test steps
    #         executor_tools: Available executor tools
    #         attempt: Current attempt number (increases emphasis for subsequent attempts)
    #         missing_or_invalid_steps: Step numbers that were missing or invalid in previous attempt
    #         parameter_mismatches: Parameter mismatches from previous attempt

    #     Returns:
    #         Formatted prompt
    #     """
    #     missing_or_invalid_steps = missing_or_invalid_steps or []
    #     parameter_mismatches = parameter_mismatches or []

    #     # Create detailed structured documentation for each tool
    #     tools_description = ""
    #     tool_details = {}  # Store details for reference in parameter mismatch error messages

    #     for tool in executor_tools:
    #         tool_name = tool.get("Tool Name", "")
    #         tool_desc = tool.get("Description", "")
    #         tool_params = tool.get("Parameters", {})
    #         tool_output = tool.get("Output", {})

    #         # Store the parameter details for this tool
    #         tool_details[tool_name] = {
    #             "params": tool_params,
    #             "param_count": len(tool_params)
    #         }

    #         # Create a clear parameter specification with required/optional information
    #         param_desc = ""

    #         # Count required parameters
    #         required_param_count = sum(1 for param_info in tool_params.values()
    #                                   if param_info.get("default") is None)

    #         # Show required parameter count clearly
    #         if required_param_count > 0:
    #             param_desc += f"    Required parameters: {required_param_count}\n"

    #         for param_name, param_info in tool_params.items():
    #             param_type = param_info.get("type", "")
    #             param_desc_text = param_info.get("description", "")
    #             is_required = param_info.get("default") is None
    #             required_tag = " (REQUIRED)" if is_required else " (optional)"
    #             param_desc += f"    - {param_name} ({param_type}){required_tag}: {param_desc_text}\n"

    #         output_desc = f"  Output: {tool_output.get('type', '')}: {tool_output.get('description', '')}\n"

    #         tools_description += f"- {tool_name}: {tool_desc}\n"
    #         if param_desc:
    #             tools_description += f"  Parameters:\n{param_desc}\n"
    #         tools_description += output_desc

    #     # Format the test steps for the prompt with explicit numbering
    #     steps_description = json.dumps(parsed_test, indent=2)

    #     # Count the number of steps in the parsed test for emphasis
    #     step_count = len(parsed_test.get("steps", []))
    #     original_steps = parsed_test.get("steps", [])

    #     # Create specific feedback about previous failures
    #     error_feedback = ""
    #     if attempt > 1:
    #         error_feedback = "ERRORS FROM PREVIOUS ATTEMPT:\n"

    #         # Missing or invalid steps feedback
    #         if missing_or_invalid_steps:
    #             error_feedback += "Missing or invalid steps:\n"
    #             for step_num in missing_or_invalid_steps:
    #                 step_index = step_num - 1
    #                 if 0 <= step_index < len(original_steps):
    #                     step = original_steps[step_index]
    #                     step_desc = step.get("description", "Unknown step")
    #                     step_action = step.get("action", "Unknown action")
    #                     error_feedback += f"- Step {step_num}: {step_desc} (Action: {step_action})\n"
    #                 else:
    #                     error_feedback += f"- Step {step_num}: Missing\n"

    #         # Parameter mismatch feedback
    #         if parameter_mismatches:
    #             error_feedback += "\nParameter mismatches:\n"
    #             for mismatch in parameter_mismatches:
    #                 step_num = mismatch.get("step_num", "Unknown")
    #                 tool = mismatch.get("tool", "Unknown tool")
    #                 expected = mismatch.get("expected_params", "Unknown")
    #                 actual = mismatch.get("actual_params", "Unknown")

    #                 # Get tool parameter details if available
    #                 tool_info = tool_details.get(tool, {})
    #                 param_info = ""
    #                 if tool_info:
    #                     param_names = list(tool_info.get("params", {}).keys())
    #                     param_info = f" (Expected parameters: {', '.join(param_names)})"

    #                 error_feedback += f"- Step {step_num} using tool '{tool}'{param_info}: Provided {actual} parameters, expected {expected}\n"

    #         error_feedback += "\n"

    #     # Explicitly list all steps that need to be mapped
    #     explicit_steps = "# All Steps That Need To Be Mapped\n"
    #     for i, step in enumerate(original_steps, 1):
    #         step_desc = step.get("description", "Unknown step")
    #         step_action = step.get("action", "Unknown action")
    #         step_element = step.get("element", "Unknown element")
    #         test_data = step.get("test_data", {})

    #         # Format test data if present
    #         test_data_str = ""
    #         if test_data:
    #             test_data_str = f" with data: {json.dumps(test_data)}"

    #         # Highlight steps that were missing or had parameter issues
    #         highlight = ""
    #         if i in missing_or_invalid_steps:
    #             highlight = " [THIS STEP WAS MISSING OR INVALID IN PREVIOUS ATTEMPT]"
                
    #         explicit_steps += f"{i}. Action: {step_action} on {step_element}{test_data_str} - {step_desc}{highlight}\n"
        
    #     # Tool usage examples based on common actions
    #     tool_examples = """
    #     # Tool Usage Examples
    #     Here are examples of how to map common actions to tools:
        
    #     1. For a "tap" action on a button:
    #        ```json
    #        {
    #          "step_num": 1,
    #          "step": { /* original step data */ },
    #          "mapped_tool": "single_tap",
    #          "arguments": ["button_id"]
    #        }
    #        ```
           
    #     2. For an "input_text" action:
    #        ```json
    #        {
    #          "step_num": 2,
    #          "step": { /* original step data */ },
    #          "mapped_tool": "send_keys",
    #          "arguments": ["input_field_id", "text to enter"]
    #        }
    #        ```
           
    #     3. For a "verify" action:
    #        ```json
    #        {
    #          "step_num": 3,
    #          "step": { /* original step data */ },
    #          "mapped_tool": "element_is_displayed",
    #          "arguments": ["element_id"]
    #        }
    #        ```
    #     """

    #     # Create the prompt with increased emphasis on parameter matching
    #     prompt = f"""
    #     You are an expert test automation engineer who maps high-level test steps to executable tool commands.

    #     {error_feedback}

    #     # Available Tools with Parameter Specifications
    #     These are the tools available for executing test steps:

    #     {tools_description}

    #     # Parsed Test Steps
    #     Here are the parsed test steps that need to be mapped to executable tool commands:

    #     ```json
    #     {steps_description}
    #     ```

    #     # Number of Steps
    #     There are exactly {step_count} test steps in total.
    #     Your output MUST contain exactly {step_count} mapped steps, no more and no less.

    #     {explicit_steps}

    #     {tool_examples if attempt > 1 else ""}

    #     # Task
    #     Map each test step to the most appropriate tool and specify the required arguments.

    #     Return the mapped steps as a JSON array with the following structure for each step:
    #     ```json
    #     [
    #       {{
    #         "step_num": 1,
    #         "step": {{...}},  // Original step from the parsed test
    #         "mapped_tool": "tool_name",
    #         "arguments": ["arg1", "arg2", ...]  // Arguments for the tool
    #       }},
    #       ...
    #     ]
    #     ```

    #     # Critical Requirements
    #     - You MUST map ALL {step_count} steps from the parsed test. Do not skip any steps.
    #     - Each step must have a "step_num" that matches its position (1 to {step_count}).
    #     - Each step must include the original step data in the "step" field.
    #     - Each step must have a valid "mapped_tool" from the available tools list.
    #     - Each step must have the EXACT number of arguments expected by the tool.
    #     - Check the parameter count carefully for each tool before mapping.
    #     - Match the parameter types described in the tool documentation.
    #     - For tap actions, use the single_tap tool (requires element identifier).
    #     - For text input, use the send_keys tool (requires element identifier and text).
    #     - For verification steps, use element_is_displayed (requires element identifier).

    #     Return only the JSON array without any explanations.
    #     """

    #     return prompt

    """
    Enhanced prompt for the Implementor Agent to better handle validation steps.
    This can be incorporated into the `_create_mapping_prompt` method in implementor_agent.py.
    """

    def create_enhanced_mapping_prompt(
        parsed_test: Dict[str, Any],
        executor_tools: List[Dict[str, Any]],
        attempt: int = 1,
        missing_or_invalid_steps: List[int] = None,
        parameter_mismatches: List[Dict[str, Any]] = None
    ) -> str:
        missing_or_invalid_steps = missing_or_invalid_steps or []
        parameter_mismatches = parameter_mismatches or []

        # Create detailed structured documentation for each tool
        tools_description = ""
        tool_details = {}  # Store details for reference

        for tool in executor_tools:
            tool_name = tool.get("Tool Name", "")
            tool_desc = tool.get("Description", "")
            tool_params = tool.get("Parameters", {})
            tool_output = tool.get("Output", {})
            
            # Store the parameter details for this tool
            tool_details[tool_name] = {
                "params": tool_params,
                "param_count": len(tool_params)
            }
            
            # Create a clear parameter specification
            param_desc = ""
            
            # Count required parameters
            required_param_count = sum(1 for param_info in tool_params.values()
                                    if param_info.get("default") is None)
            
            # Show required parameter count clearly
            if required_param_count > 0:
                param_desc += f"    Required parameters: {required_param_count}\n"

            for param_name, param_info in tool_params.items():
                param_type = param_info.get("type", "")
                param_desc_text = param_info.get("description", "")
                is_required = param_info.get("default") is None
                required_tag = " (REQUIRED)" if is_required else " (optional)"
                param_desc += f"    - {param_name} ({param_type}){required_tag}: {param_desc_text}\n"
            
            output_desc = f"  Output: {tool_output.get('type', '')}: {tool_output.get('description', '')}\n"
            
            tools_description += f"- {tool_name}: {tool_desc}\n"
            if param_desc:
                tools_description += f"  Parameters:\n{param_desc}\n"
            tools_description += output_desc
        
        # Format the test steps for the prompt with explicit numbering
        steps_description = json.dumps(parsed_test, indent=2)
        
        # Count the number of steps in the parsed test for emphasis
        step_count = len(parsed_test.get("steps", []))
        original_steps = parsed_test.get("steps", [])
        
        # Create specific feedback about previous failures
        error_feedback = ""
        if attempt > 1:
            error_feedback = "ERRORS FROM PREVIOUS ATTEMPT:\n"
            
            # Missing or invalid steps feedback
            if missing_or_invalid_steps:
                error_feedback += "Missing or invalid steps:\n"
                for step_num in missing_or_invalid_steps:
                    step_index = step_num - 1
                    if 0 <= step_index < len(original_steps):
                        step = original_steps[step_index]
                        step_desc = step.get("description", "Unknown step")
                        step_action = step.get("action", "Unknown action")
                        error_feedback += f"- Step {step_num}: {step_desc} (Action: {step_action})\n"
                    else:
                        error_feedback += f"- Step {step_num}: Missing\n"

            # Parameter mismatch feedback
            if parameter_mismatches:
                error_feedback += "\nParameter mismatches:\n"
                for mismatch in parameter_mismatches:
                    step_num = mismatch.get("step_num", "Unknown")
                    tool = mismatch.get("tool", "Unknown tool")
                    expected = mismatch.get("expected_params", "Unknown")
                    actual = mismatch.get("actual_params", "Unknown")

                    # Get tool parameter details if available
                    tool_info = tool_details.get(tool, {})
                    param_info = ""
                    if tool_info:
                        param_names = list(tool_info.get("params", {}).keys())
                        param_info = f" (Expected parameters: {', '.join(param_names)})"

                    error_feedback += f"- Step {step_num} using tool '{tool}'{param_info}: Provided {actual} parameters, expected {expected}\n"
                    
            error_feedback += "\n"

        # Explicitly list all steps that need to be mapped
        explicit_steps = "# All Steps That Need To Be Mapped\n"
        for i, step in enumerate(original_steps, 1):
            step_desc = step.get("description", "Unknown step")
            step_action = step.get("action", "Unknown action")
            step_element = step.get("element", "Unknown element")
            test_data = step.get("test_data", {})
            step_type = step.get("step_type", "Given")

            # Format test data if present
            test_data_str = ""
            if test_data:
                test_data_str = f" with data: {json.dumps(test_data)}"

            # Highlight steps that were missing or had parameter issues
            highlight = ""
            if i in missing_or_invalid_steps:
                highlight = " [THIS STEP WAS MISSING OR INVALID IN PREVIOUS ATTEMPT]"

            explicit_steps += f"{i}. Type: {step_type}, Action: {step_action} on {step_element}{test_data_str} - {step_desc}{highlight}\n"

        # Enhanced validation mapping examples
        validation_examples = """
        # Validation Step Mapping Examples
        Here are examples of how to map different validation/assertion steps:

        1. Screen Validation:
        When the step contains "should be on the X screen" or similar:
        ```json
        {
            "step_num": 3,
            "step": { "step_type": "Then", "description": "I should be on the \"Home Screen\"" },
            "mapped_tool": "verify_current_screen",
            "arguments": ["Home Screen"]
        }
        ```

        2. Text Content Validation:
        When the step contains "should see [text]" or similar:
        ```json
        {
            "step_num": 4,
            "step": { "step_type": "Then", "description": "I should see \"Welcome message\"" },
            "mapped_tool": "verify_text_displayed",
            "arguments": ["Welcome message"]
        }
        ```

        3. Element Text Validation:
        When the step contains "should see [element] with [text]" or similar:
        ```json
        {
            "step_num": 5,
            "step": { "step_type": "Then", "description": "I should see profile name with \"John Doe\"" },
            "mapped_tool": "verify_element_text",
            "arguments": ["profile_name", "John Doe"]
        }
        ```

        4. Location Validation:
        When the step contains "should see the selected location" or similar:
        ```json
        {
            "step_num": 6,
            "step": { "step_type": "Then", "description": "I should see the selected location displayed" },
            "mapped_tool": "verify_displayed_location",
            "arguments": ["Indiranagar, Bengaluru"]
        }
        ```

        5. Element Visibility Validation:
        When the step contains "should see element" or similar:
        ```json
        {
            "step_num": 7,
            "step": { "step_type": "Then", "description": "I should see the login button" },
            "mapped_tool": "element_is_displayed",
            "arguments": ["login_button"]
        }
        ```
        """

        # Tool usage examples for common actions
        tool_examples = """
        # General Tool Usage Examples
        Here are examples of how to map common actions to tools:

        1. For a "tap" action on a button:
        ```json
        {
            "step_num": 1,
            "step": { "step_type": "When", "description": "I tap on the login button" },
            "mapped_tool": "single_tap",
            "arguments": ["login_button"]
        }
        ```

        2. For an "input_text" action:
        ```json
        {
            "step_num": 2,
            "step": { "step_type": "When", "description": "I enter email in the email field" },
            "mapped_tool": "send_keys",
            "arguments": ["email_field", "test@example.com"]
        }
        ```
        """

        # Validation tools specific guidance
        validation_tools_guidance = """
        # Validation Tools Guidance

        When mapping validation steps (typically 'Then' steps), choose the most appropriate validation tool:

        1. `verify_current_screen` - For validating the current screen matches expected
        - Use for steps like: "I should be on the X screen"
        - Arguments: [screen_name]

        2. `verify_text_displayed` - For validating text appears anywhere on screen
        - Use for steps like: "I should see X"
        - Arguments: [expected_text, exact_match (optional)]

        3. `verify_element_text` - For validating specific element contains text
        - Use for steps like: "I should see X with text Y"
        - Arguments: [element_id, expected_text, exact_match (optional)]

        4. `verify_displayed_location` - For location-specific validation
        - Use for steps like: "I should see the selected location displayed"
        - Arguments: [expected_location]

        5. `element_is_displayed` - For validating element visibility
        - Use for steps like: "I should see the X button/element"
        - Arguments: [element_id, timeout (optional)]

        6. `verify_complex_condition` - For complex validations requiring multiple checks
        - Use for complex conditions or app-specific validations
        - Arguments: [condition_type, expected_value]

        IMPORTANT: Try to extract the expected values from the test step or test data.
        For location validation, use the location value from previous steps if available.
        """

        # Create the prompt with increased emphasis on validation mapping
        prompt = f"""
        You are an expert test automation engineer who maps high-level test steps to executable tool commands.

        {error_feedback}

        # Available Tools with Parameter Specifications
        These are the tools available for executing test steps:

        {tools_description}

        # Parsed Test Steps
        Here are the parsed test steps that need to be mapped to executable tool commands:

        ```json
        {steps_description}
        ```

        # Number of Steps
        There are exactly {step_count} test steps in total.
        Your output MUST contain exactly {step_count} mapped steps, no more and no less.

        {explicit_steps}

        {validation_tools_guidance}

        {validation_examples}

        {tool_examples}

        # Task
        Map each test step to the most appropriate tool and specify the required arguments.

        Pay special attention to validation steps (usually starting with "Then"):
        1. Analyze the context to determine what is being validated
        2. Extract any expected values from the step or from previous steps
        3. Use the most precise validation tool for the task
        4. For location validation, reference the location data from previous steps

        Return the mapped steps as a JSON array with the following structure for each step:
        ```json
        [
        {{
            "step_num": 1,
            "step": {{...}},  // Original step from the parsed test
            "mapped_tool": "tool_name",
            "arguments": ["arg1", "arg2", ...]  // Arguments for the tool
        }},
        ...
        ]
        ```

        # Critical Requirements
        - You MUST map ALL {step_count} steps from the parsed test. Do not skip any steps.
        - Each step must have a "step_num" that matches its position (1 to {step_count}).
        - Each step must include the original step data in the "step" field.
        - Each step must have a valid "mapped_tool" from the available tools list.
        - Each step must have the EXACT number of arguments expected by the tool.
        - Validation steps ("Then") must use appropriate validation tools, not action tools.
        - Check the parameter count carefully for each tool before mapping.
        - Match the parameter types described in the tool documentation.

        Return only the JSON array without any explanations.
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
                {"role": "system", "content": "You are an expert test automation engineer who maps high-level test steps to executable tool commands."},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm.generate_response(messages)
            return response.content
            
        except Exception as e:
            logger.warning(f"Error getting LLM response: {str(e)}")
            return ""
    
    def _validate_mapped_steps(
        self, 
        mapped_steps: List[Dict[str, Any]], 
        original_steps: List[Dict[str, Any]],
        executor_tools: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate mapped steps to ensure all original steps are accounted for.
        
        Args:
            mapped_steps: The mapped steps to validate
            original_steps: The original steps from the parser
            executor_tools: Available executor tools for parameter validation
            
        Returns:
            Dictionary with validation result and details of issues
        """
        result = {
            "valid": False,
            "missing_or_invalid_steps": [],
            "parameter_mismatches": []
        }
        
        # Create tool parameter map for validation
        tool_param_map = {}
        if executor_tools:
            for tool in executor_tools:
                tool_name = tool.get("Tool Name", "")
                if tool_name:
                    params = tool.get("Parameters", {})
                    # Count required parameters (those without defaults)
                    required_params = sum(1 for param_info in params.values() 
                                         if param_info.get("default") is None)
                    tool_param_map[tool_name] = {
                        "params": params,
                        "param_count": len(params),
                        "required_params": required_params
                    }
        
        # Check basic structure
        if not isinstance(mapped_steps, list):
            logger.warning("Mapped steps is not a list")
            result["missing_or_invalid_steps"] = list(range(1, len(original_steps) + 1))
            return result
            
        # Check step count
        if len(mapped_steps) != len(original_steps):
            logger.warning(f"Mapped step count ({len(mapped_steps)}) does not match original step count ({len(original_steps)})")
            # Identify which steps are missing
            mapped_step_nums = [step.get("step_num") for step in mapped_steps if isinstance(step, dict)]
            expected_step_nums = set(range(1, len(original_steps) + 1))
            result["missing_or_invalid_steps"] = list(expected_step_nums - set(mapped_step_nums))
            return result
            
        # Check that each step has the required fields
        step_nums_seen = set()
        
        for i, step in enumerate(mapped_steps):
            if not isinstance(step, dict):
                logger.warning(f"Step {i+1} is not a dictionary")
                result["missing_or_invalid_steps"].append(i+1)
                continue
                
            # Get step number first to use in error messages
            step_num = step.get("step_num")
            if not isinstance(step_num, int) or step_num < 1 or step_num > len(original_steps):
                logger.warning(f"Invalid step_num {step_num} in position {i+1}")
                result["missing_or_invalid_steps"].append(i+1)
                continue
            
            # Check required fields
            missing_fields = []
            for field in ["step_num", "mapped_tool", "arguments", "step"]:
                if field not in step:
                    missing_fields.append(field)
                    
            if missing_fields:
                logger.warning(f"Missing fields in step {step_num}: {', '.join(missing_fields)}")
                result["missing_or_invalid_steps"].append(step_num)
                continue
                
            # Check for duplicate step_num
            if step_num in step_nums_seen:
                logger.warning(f"Duplicate step_num {step_num}")
                result["missing_or_invalid_steps"].append(step_num)
                continue
                
            step_nums_seen.add(step_num)
            
            # Check if arguments is a list
            if not isinstance(step["arguments"], list):
                logger.warning(f"'arguments' field is not a list in step {step_num}")
                result["missing_or_invalid_steps"].append(step_num)
                continue
            
            # Validate parameter count against tool requirements
            mapped_tool = step["mapped_tool"]
            if mapped_tool in tool_param_map:
                tool_info = tool_param_map[mapped_tool]
                argument_count = len(step["arguments"])
                expected_count = tool_info["param_count"]
                required_count = tool_info["required_params"]
                
                # Check if the number of arguments matches the expected parameters
                if argument_count < required_count or argument_count > expected_count:
                    logger.warning(
                        f"Step {step_num}: Tool '{mapped_tool}' expects {required_count}-{expected_count} "
                        f"parameters, but got {argument_count}"
                    )
                    # Record the parameter mismatch
                    result["parameter_mismatches"].append({
                        "step_num": step_num,
                        "tool": mapped_tool,
                        "expected_params": f"{required_count}-{expected_count}",
                        "actual_params": argument_count
                    })
                    continue
            else:
                logger.warning(f"Unknown tool '{mapped_tool}' in step {step_num}")
                result["missing_or_invalid_steps"].append(step_num)
                continue
                
        # Check that all step numbers from 1 to len(original_steps) are present
        expected_step_nums = set(range(1, len(original_steps) + 1))
        if step_nums_seen != expected_step_nums:
            missing_steps = expected_step_nums - step_nums_seen
            logger.warning(f"Missing step numbers: {missing_steps}")
            result["missing_or_invalid_steps"].extend(list(missing_steps))
            return result
        
        # If we've made it here with no issues in missing_or_invalid_steps and parameter_mismatches,
        # the validation is successful
        if not result["missing_or_invalid_steps"] and not result["parameter_mismatches"]:
            result["valid"] = True
            
        return result