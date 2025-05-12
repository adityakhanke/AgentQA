"""
Checker Agent: Helps find UI elements when standard locators fail.

This agent analyzes page source and uses LLM reasoning to find alternative
locators for elements that could not be found with the standard approaches.
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple, Union

from agents.base_agent import BaseAgent
from core.context_manager import ContextManager
from core.error_handler import handle_error
from tools.tool_registry import get_tool_function, get_tools_for_agent
from utils.logger import get_logger
from utils.extract_json import extract_json

# Configure logger
logger = get_logger(__name__)

class CheckerAgent(BaseAgent):
    """
    Agent responsible for finding UI elements when standard locators fail.
    """
    
    def __init__(
        self,
        name: str,
        llm_config: Dict[str, Any],
        context_manager: ContextManager
    ):
        """
        Initialize the checker agent.
        
        Args:
            name: Agent name
            llm_config: LLM configuration
            context_manager: Context manager for shared state
        """
        super().__init__(name, llm_config, context_manager)
        self.tools = get_tools_for_agent("checker")
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Find an alternative locator for a UI element.
        
        Args:
            input_data: Input data containing information about the missing element
                - missing_element: The element that could not be found
                - error_message: Error message from the failed operation
                - page_source: Current page source
                
        Returns:
            Dictionary containing the alternative locator
        """
        try:
            # Extract input data
            missing_element = input_data.get("missing_element")
            error_message = input_data.get("error_message", "")
            page_source = input_data.get("page_source", "")
            
            if not missing_element:
                return {"error": "No missing element provided"}

            if not page_source:
                return {"error": "No page source provided"}
                
            # Try to find similar elements in the page source
            similar_elements = await self._find_similar_elements(missing_element, page_source)

            if similar_elements:
                # If similar elements found, return the best match
                best_match = similar_elements[0]
                logger.info(f"Found similar element: {best_match}")
                
                # Determine the type of locator (resource-id, text, xpath)
                if "resource-id" in best_match:
                    return {"resource-id": best_match["resource-id"]}
                elif "text" in best_match:
                    return {"text": best_match["text"]}
                else:
                    return {"xpath": best_match["xpath"]}
            
            # If no similar elements found, try using LLM to find an alternative
            llm_suggestion = await self._get_llm_suggestion(missing_element, error_message, page_source)
            
            if llm_suggestion:
                logger.info(f"LLM suggested alternative: {llm_suggestion}")
                return llm_suggestion
                
            # If all else fails, return an empty result
            logger.warning(f"No alternative found for missing element: {missing_element}")
            return {}
            
        except Exception as e:
            error_details = handle_error(e, "Element checking failed")
            logger.error(error_details["message"], exc_info=True)
            
            return {"error": error_details["message"]}
    
    async def _find_similar_elements(
        self,
        missing_element: str, 
        page_source: str
    ) -> List[Dict[str, str]]:
        """
        Find elements similar to the missing element in the page source.

        Args:
            missing_element: The element that could not be found
            page_source: Current page source
            
        Returns:
            List of similar elements with scores
        """
        similar_elements = []
        
        # Extract resource IDs from page source
        resource_ids = self._extract_resource_ids(page_source)
        for resource_id in resource_ids:
            similarity = self._calculate_similarity(missing_element, resource_id)
            if similarity > 0.6:  # Threshold for similarity
                similar_elements.append({
                    "resource-id": resource_id,
                    "similarity": similarity
                })
                
        # Extract text values from page source
        texts = self._extract_texts(page_source)
        for text in texts:
            similarity = self._calculate_similarity(missing_element, text)
            if similarity > 0.6:  # Threshold for similarity
                similar_elements.append({
                    "text": text,
                    "similarity": similarity
                })
                
        # Sort by similarity score (descending)
        similar_elements.sort(key=lambda x: x["similarity"], reverse=True)
        
        return similar_elements

    def _extract_resource_ids(self, page_source: str) -> List[str]:
        """
        Extract resource IDs from page source.
        
        Args:
            page_source: Page source to extract from

        Returns:
            List of resource IDs
        """
        # Extract resource-id attributes
        resource_id_pattern = r'resource-id="([^"]*)"'
        resource_ids = re.findall(resource_id_pattern, page_source)

        # Make unique list
        return list(set(resource_ids))
    
    def _extract_texts(self, page_source: str) -> List[str]:
        """
        Extract text values from page source.
        
        Args:
            page_source: Page source to extract from
            
        Returns:
            List of text values
        """
        # Extract text attributes
        text_pattern = r'text="([^"]*)"'
        texts = re.findall(text_pattern, page_source)

        # Extract content-desc attributes
        content_desc_pattern = r'content-desc="([^"]*)"'
        content_descs = re.findall(content_desc_pattern, page_source)
        
        # For iOS
        label_pattern = r'label="([^"]*)"'
        labels = re.findall(label_pattern, page_source)
        
        name_pattern = r'name="([^"]*)"'
        names = re.findall(name_pattern, page_source)
        
        # Combine and make unique list
        all_texts = texts + content_descs + labels + names
        return [text for text in list(set(all_texts)) if text]  # Filter out empty strings
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate string similarity between two strings.

        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity score between 0 and 1
        """
        import difflib
        return difflib.SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
    
    async def _get_llm_suggestion(
        self,
        missing_element: str, 
        error_message: str, 
        page_source: str
    ) -> Optional[Dict[str, str]]:
        """
        Get LLM suggestion for an alternative locator.
        
        Args:
            missing_element: The element that could not be found
            error_message: Error message from the failed operation
            page_source: Current page source
            
        Returns:
            Dictionary containing the alternative locator or None if not found
        """
        try:
            # Prepare prompt for LLM
            prompt = self._create_element_finding_prompt(missing_element, error_message, page_source)

            # Get LLM response
            llm_response = await self._get_llm_response(prompt)
            
            # Extract JSON from response
            suggestion = extract_json(llm_response)
            if suggestion:
                return suggestion
                
            # If no JSON found, try to extract key-value pairs from the response
            return self._extract_locator_from_text(llm_response)

        except Exception as e:
            logger.warning(f"Error getting LLM suggestion: {str(e)}")
            return None
    
    def _create_element_finding_prompt(
        self,
        missing_element: str, 
        error_message: str, 
        page_source: str
    ) -> str:
        """
        Create a prompt for the LLM to find an alternative locator.

        Args:
            missing_element: The element that could not be found
            error_message: Error message from the failed operation
            page_source: Current page source

        Returns:
            Formatted prompt
        """
        # Truncate page source to a reasonable size if needed
        max_page_source_length = 5000
        if len(page_source) > max_page_source_length:
            truncated_page_source = page_source[:max_page_source_length] + "... (truncated)"
        else:
            truncated_page_source = page_source

        prompt = f"""
        You are an expert in mobile UI testing and element identification.
        
        I'm trying to find an element with identifier: '{missing_element}' but received this error:
        {error_message}

        Here is the current page source:
        
        ```xml
        {truncated_page_source}
        ```

        Please analyze the page source and suggest the best alternative element locator that most closely matches '{missing_element}'.
        
        Return your answer in JSON format with one of the following fields:
        - "resource-id": if you find a matching resource ID
        - "text": if you find matching text content
        - "xpath": if you need to provide an XPath expression
        
        Example response:
        ```json
        {{"resource-id": "com.example.app:id/login_button"}}
        ```
        
        or:
        
        ```json
        {{"text": "Login"}}
        ```
        
        or:
        
        ```json
        {{"xpath": "//android.widget.Button[@content-desc='Login']"}}
        ```
        
        Focus on finding the most reliable locator that will uniquely identify the element.
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
                {"role": "system", "content": "You are an expert in mobile UI testing and element identification."},
                {"role": "user", "content": prompt}
            ]

            response = await self.llm.generate_response(messages)
            return response.content

        except Exception as e:
            logger.warning(f"Error getting LLM response: {str(e)}")
            return ""

    def _extract_locator_from_text(self, text: str) -> Optional[Dict[str, str]]:
        """
        Extract locator information from text response.

        Args:
            text: Text to extract from

        Returns:
            Dictionary containing the locator or None if not found
        """
        # Try to find resource-id
        resource_id_match = re.search(r'resource-id["\']?\s*:\s*["\']([^"\']+)["\']', text)
        if resource_id_match:
            return {"resource-id": resource_id_match.group(1)}

        # Try to find text
        text_match = re.search(r'text["\']?\s*:\s*["\']([^"\']+)["\']', text)
        if text_match:
            return {"text": text_match.group(1)}

        # Try to find xpath
        xpath_match = re.search(r'xpath["\']?\s*:\s*["\']([^"\']+)["\']', text)
        if xpath_match:
            return {"xpath": xpath_match.group(1)}

        return None


"""
Executor Agent: Executes test steps using mobile interaction tools.

This agent is responsible for executing test steps by utilizing the
registered tools based on the test plan provided by the Implementor Agent.
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional, Union

from agents.base_agent import BaseAgent
from core.context_manager import ContextManager
from core.error_handler import handle_error
from tools.session_management import load_app, page_source
from tools.tool_registry import get_tool_function, get_tools_for_agent
from utils.logger import get_logger
from utils.extract_json import extract_json
from utils.screenshot_manager import ScreenshotManager

# Configure logger
logger = get_logger(__name__)

class ExecutorAgent(BaseAgent):
    """
    Agent responsible for executing test steps using registered tools.
    """
    
    def __init__(
        self,
        name: str,
        llm_config: Dict[str, Any],
        context_manager: ContextManager,
        checker_agent=None,
        max_retries: int = 3
    ):
        """
        Initialize the executor agent.
        
        Args:
            name: Agent name
            llm_config: LLM configuration
            context_manager: Context manager for shared state
            checker_agent: Checker agent for element validation
            max_retries: Maximum number of retries for failed steps
        """
        super().__init__(name, llm_config, context_manager)
        self.checker_agent = checker_agent
        self.max_retries = max_retries
        self.tools = get_tools_for_agent("executor")
        self.screenshot_manager = None
        self.test_results = []
        self.current_test_case = None
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a test plan.
        
        Args:
            input_data: Input data containing the test plan
                - test_plan: The test plan to execute
                
        Returns:
            Dictionary containing the execution results
        """
        try:
            # Extract the test plan from input data
            if isinstance(input_data, str):
                # Try to extract JSON from string if needed
                test_plan = extract_json(input_data)
                if not test_plan:
                    test_plan = json.loads(input_data)
            else:
                test_plan = input_data.get("test_plan")
                
            if not test_plan:
                return {"status": "error", "message": "No test plan provided"}
                
            # Initialize the execution context
            self.test_results = []
            self.current_test_case = None
            
            # Initialize Appium session
            session_result = await load_app()
            if session_result.get("message") != "Success":
                return {
                    "status": "error",
                    "message": f"Failed to initialize Appium session: {session_result.get('error', 'Unknown error')}"
                }
                
            driver = session_result["driver"]
            
            # Initialize screenshot manager
            self.screenshot_manager = ScreenshotManager(driver)

            # Take initial screenshot
            initial_screenshot = self.screenshot_manager.take_screenshot("initial_state")
            
            # Execute the test plan
            return await self._execute_test_plan(test_plan)
                
        except Exception as e:
            error_details = handle_error(e, "Test execution failed")
            logger.error(error_details["message"], exc_info=True)
            
            return {
                "status": "error",
                "message": error_details["message"],
                "traceback": error_details.get("traceback")
            }
            
    async def _execute_test_plan(self, test_plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute a test plan consisting of multiple steps.

        Args:
            test_plan: List of test steps to execute
            
        Returns:
            Dictionary containing the execution results
        """
        if not isinstance(test_plan, list):
            return {
                "status": "error",
                "message": f"Invalid test plan format: expected list, got {type(test_plan).__name__}"
            }
            
        execution_results = {
            "status": "pass",
            "steps": [],
            "start_time": time.time(),
            "end_time": None,
            "duration_seconds": 0,
            "screenshots": [],
            "failed_steps": 0
        }
        
        # Track initial screenshot
        if self.screenshot_manager:
            initial_screenshot = self.screenshot_manager.take_screenshot("test_start")
            execution_results["screenshots"].append(initial_screenshot)
        
        # Execute each step in the test plan
        for step_num, step in enumerate(test_plan, 1):
            step_result = await self._execute_step(step, step_num)
            execution_results["steps"].append(step_result)
            
            # Add screenshot to results if available
            if step_result.get("screenshot"):
                execution_results["screenshots"].append(step_result["screenshot"])
                
            # Update overall status if step failed
            if step_result["status"] != "pass":
                execution_results["status"] = "fail"
                execution_results["failed_steps"] += 1
                
                # Take screenshot of failure state
                if self.screenshot_manager:
                    failure_screenshot = self.screenshot_manager.take_screenshot(f"failure_step_{step_num}")
                    execution_results["screenshots"].append(failure_screenshot)
                    
                # Check if we should stop execution
                if self.context_manager.get("fail_fast", False):
                    logger.warning(f"Stopping test execution due to step failure (fail_fast=True)")
                    break
        
        # Take final screenshot
        if self.screenshot_manager:
            final_screenshot = self.screenshot_manager.take_screenshot("test_end")
            execution_results["screenshots"].append(final_screenshot)
            
        # Update execution timing
        execution_results["end_time"] = time.time()
        execution_results["duration_seconds"] = execution_results["end_time"] - execution_results["start_time"]
        
        # Add execution summary
        execution_results["summary"] = {
            "total_steps": len(test_plan),
            "executed_steps": len(execution_results["steps"]),
            "passed_steps": len(execution_results["steps"]) - execution_results["failed_steps"],
            "failed_steps": execution_results["failed_steps"],
            "pass_percentage": (len(execution_results["steps"]) - execution_results["failed_steps"]) / len(execution_results["steps"]) * 100 if execution_results["steps"] else 0
        }
        
        return execution_results
            
    async def _execute_step(
        self, 
        step: Dict[str, Any],
        step_num: int
    ) -> Dict[str, Any]:
        """
        Execute a single test step.
        
        Args:
            step: Test step to execute
            step_num: Step number for logging
            
        Returns:
            Dictionary containing the step execution result
        """
        # Extract step information
        original_step = step.get("step", {})
        description = original_step.get("description", f"Step {step_num}")
        tool_name = step.get("mapped_tool")
        arguments = step.get("arguments", [])
        
        logger.info(f"Executing step {step_num}: {description} using {tool_name}")
        
        # Initialize step result
        step_result = {
            "step_num": step_num,
            "description": description,
            "tool": tool_name,
            "arguments": arguments,
            "status": "pass",
            "error": None,
            "message": "",
            "screenshot": None,
            "retry_count": 0,
            "start_time": time.time(),
            "end_time": None,
            "duration_seconds": 0
        }
        
        # Take screenshot before execution if configured
        if self.screenshot_manager and self.context_manager.get("screenshot_on_step", True):
            before_screenshot = self.screenshot_manager.take_screenshot(f"before_step_{step_num}")
        
        # Find the tool function
        tool_func = get_tool_function("executor", tool_name)
        if not tool_func:
            step_result["status"] = "error"
            step_result["error"] = f"Tool not found: {tool_name}"
            step_result["message"] = f"No tool available to execute this step"
            logger.error(f"Tool not found: {tool_name}")
            return self._finalize_step_result(step_result)
        
        # Execute the step with retries
        retry_count = 0
        max_retries = self.max_retries
        
        while retry_count <= max_retries:
            try:
                # Log the execution attempt
                if retry_count > 0:
                    logger.info(f"Retry #{retry_count} for step {step_num}")
                    step_result["retry_count"] = retry_count
                
                # Execute the tool with arguments
                if isinstance(arguments, list):
                    result = await tool_func(*arguments)
                elif isinstance(arguments, dict):
                    result = await tool_func(**arguments)
                else:
                    result = await tool_func()
                
                # Check result status
                if result.get("message") == "Success":
                    step_result["status"] = "pass"
                    step_result["message"] = result.get("details", "Step executed successfully")
                    break
                else:
                    step_result["status"] = "fail"
                    step_result["error"] = result.get("error", "Unknown error")
                    step_result["message"] = f"Step execution failed: {step_result['error']}"
                    
                    # If element not found and checker agent is available, try to correct the element
                    if "not found" in step_result["error"] and self.checker_agent and retry_count < max_retries:
                        # Get current page source for analysis
                        page_src = await page_source()
                        
                        # Try to get a corrected element from the checker agent
                        corrected_element = await self._get_corrected_element(
                            arguments, step_result["error"], page_src.get("body", "")
                        )
                        
                        if corrected_element:
                            logger.info(f"Checker agent suggested corrected element: {corrected_element}")
                            
                            # Update arguments with corrected element
                            if isinstance(arguments, list) and len(arguments) > 0:
                                arguments[0] = corrected_element
                            elif isinstance(arguments, dict) and "search_key" in arguments:
                                arguments["search_key"] = corrected_element
                                
                            # Retry with corrected element
                            retry_count += 1
                            await asyncio.sleep(1)  # Short delay before retry
                            continue
                            
                    # If retry limit reached or no correction found, break the loop
                    if retry_count >= max_retries:
                        break
                    
                    # Wait before retry
                    retry_count += 1
                    await asyncio.sleep(1)
            
            except Exception as e:
                error_details = handle_error(e, f"Step {step_num} execution error")
                step_result["status"] = "error"
                step_result["error"] = error_details["message"]
                step_result["message"] = f"Exception occurred: {error_details['message']}"
                
                # If retry limit reached, break the loop
                if retry_count >= max_retries:
                    break
                
                # Wait before retry
                retry_count += 1
                await asyncio.sleep(1)
        
        # Take screenshot after execution if configured
        if self.screenshot_manager:
            after_screenshot = self.screenshot_manager.take_screenshot(
                f"{'error' if step_result['status'] != 'pass' else 'after'}_step_{step_num}"
            )
            step_result["screenshot"] = after_screenshot
        
        return self._finalize_step_result(step_result)
    
    def _finalize_step_result(self, step_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Finalize the step result by adding timing information.
        
        Args:
            step_result: Step result to finalize
            
        Returns:
            Finalized step result
        """
        step_result["end_time"] = time.time()
        step_result["duration_seconds"] = step_result["end_time"] - step_result["start_time"]
        
        # Log the result
        if step_result["status"] == "pass":
            logger.info(f"Step {step_result['step_num']} passed: {step_result['description']}")
        else:
            logger.error(f"Step {step_result['step_num']} failed: {step_result['description']} - {step_result['error']}")
            
        return step_result
    
    async def _get_corrected_element(
        self, 
        arguments: Union[List, Dict],
        error_message: str, 
        page_source: str
    ) -> Optional[str]:
        """
        Get corrected element from the checker agent.
        
        Args:
            arguments: Arguments to the tool
            error_message: Error message from the tool
            page_source: Current page source

        Returns:
            Corrected element or None if not found
        """
        if not self.checker_agent:
            return None
            
        try:
            # Extract the search key from arguments
            search_key = None
            if isinstance(arguments, list) and len(arguments) > 0:
                search_key = arguments[0]
            elif isinstance(arguments, dict) and "search_key" in arguments:
                search_key = arguments["search_key"]
                
            if not search_key:
                return None
                
            # Prepare the request for the checker agent
            request = {
                "missing_element": search_key,
                "error_message": error_message,
                "page_source": page_source
            }
            
            # Call the checker agent
            response = await self.checker_agent.execute(request)
            
            # Extract the corrected element from the response
            if response and isinstance(response, dict):
                if "resource-id" in response:
                    return response["resource-id"]
                elif "text" in response:
                    return response["text"]
                elif "xpath" in response:
                    return response["xpath"]
                    
            return None
            
        except Exception as e:
            logger.warning(f"Error getting corrected element: {str(e)}")
            return None
    
    async def execute_test_case(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a complete test case.
        
        Args:
            test_case: Test case to execute
                - feature: Feature information
                - scenario: Scenario information
                - steps: List of steps to execute
                
        Returns:
            Test case execution results
        """
        try:
            self.current_test_case = test_case
            
            # Extract test case information
            feature = test_case.get("feature", {})
            scenario = test_case.get("scenario", {})
            test_plan = test_case.get("test_implementation", [])
            
            if not test_plan:
                return {
                    "status": "error",
                    "message": "No test implementation found in test case"
                }
                
            # Execute the test plan
            execution_results = await self._execute_test_plan(test_plan)
            
            # Add test case information to results
            execution_results["feature"] = feature
            execution_results["scenario"] = scenario
            
            # Store results
            self.test_results.append(execution_results)
            
            return execution_results
            
        except Exception as e:
            error_details = handle_error(e, "Test case execution failed")
            logger.error(error_details["message"], exc_info=True)
            
            # Create a minimal result with error information
            result = {
                "status": "error",
                "feature": test_case.get("feature", {}),
                "scenario": test_case.get("scenario", {}),
                "message": error_details["message"],
                "traceback": error_details.get("traceback"),
                "steps": [],
                "screenshots": []
            }
            
            # Store error result
            self.test_results.append(result)
            
            return result
    
    async def execute_test_cases(self, test_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute multiple test cases.
        
        Args:
            test_cases: List of test cases to execute
            
        Returns:
            List of test case execution results
        """
        results = []
        
        for test_case in test_cases:
            result = await self.execute_test_case(test_case)
            results.append(result)
            
        return results
    
    def get_test_results(self) -> List[Dict[str, Any]]:
        """
        Get the test results.
        
        Returns:
            List of test case execution results
        """
        return self.test_results



"""
Test Orchestrator: Coordinates the overall test execution process.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from core.agent_manager import AgentManager
from core.context_manager import ContextManager
from core.error_handler import handle_error
from gherkin.parser import GherkinParser
from tools.session_management import load_app, quit_driver
from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

class TestOrchestrator:
    """
    Orchestrates the test execution process by coordinating between agents.
    """
    
    def __init__(
        self,
        feature_path: Union[str, Path],
        context_manager: ContextManager,
        agent_manager: AgentManager,
        parser_agent,
        implementor_agent,
        executor_agent,
        reporter_agent
    ):
        """
        Initialize the test orchestrator.
        
        Args:
            feature_path: Path to Gherkin feature file or directory
            context_manager: Context manager for shared state
            agent_manager: Agent manager
            parser_agent: Parser agent
            implementor_agent: Implementor agent
            executor_agent: Executor agent
            reporter_agent: Reporter agent
        """
        self.feature_path = Path(feature_path)
        self.context_manager = context_manager
        self.agent_manager = agent_manager
        self.parser_agent = parser_agent
        self.implementor_agent = implementor_agent
        self.executor_agent = executor_agent
        self.reporter_agent = reporter_agent
        self.gherkin_parser = GherkinParser()
        
    async def run(self) -> List[Dict[str, Any]]:
        """
        Run tests based on the provided feature path.
        
        Returns:
            List of test results
        """
        try:
            # Parse feature files
            feature_files = self._get_feature_files()
            logger.info(f"Found {len(feature_files)} feature files")
            
            # Initialize Appium session
            session_result = await load_app()
            
            if session_result.get("message") != "Success":
                logger.error(f"Failed to initialize Appium session: {session_result.get('error', 'Unknown error')}")
                return []
            
            # Store the driver in the context
            self.context_manager.set("driver", session_result["driver"])
            
            # Execute each feature file
            all_results = []
            
            for feature_file in feature_files:
                logger.info(f"Processing feature file: {feature_file}")
                
                # Parse the feature file
                with open(feature_file, 'r') as f:
                    feature_content = f.read()
                    
                # Execute the feature
                results = await self._execute_feature(feature_content)
                all_results.extend(results)
                
            return all_results
            
        except Exception as e:
            error_details = handle_error(e, "Test orchestration failed")
            logger.error(error_details["message"], exc_info=True)
            return []
            
        finally:
            # Clean up
            await quit_driver()
    
    def _get_feature_files(self) -> List[Path]:
        """
        Get list of feature files from the feature path.
        
        Returns:
            List of feature file paths
        """
        if self.feature_path.is_file():
            return [self.feature_path]
            
        if self.feature_path.is_dir():
            return list(self.feature_path.glob("**/*.feature"))
            
        return []
    
    async def _execute_feature(self, feature_content: str) -> List[Dict[str, Any]]:
        """
        Execute a single feature.
        
        Args:
            feature_content: Gherkin feature content
            
        Returns:
            List of test results
        """
        try:
            # Record start time
            start_time = time.time()
            
            # Parse the feature using the parser agent
            logger.info("Parsing feature with parser agent")
            parsed_test = await self.parser_agent.execute({"test_case": feature_content})
            
            if "error" in parsed_test:
                logger.error(f"Failed to parse feature: {parsed_test['error']}")
                return []
                
            logger.info(f"Successfully parsed feature: {parsed_test.get('feature', 'Unknown')}")
            
            # Map the test steps to executable commands
            logger.info("Mapping test steps with implementor agent")
            mapped_test = await self.implementor_agent.execute({"parsed_test": parsed_test})
            
            if "error" in mapped_test:
                logger.error(f"Failed to map test steps: {mapped_test['error']}")
                return []
                
            test_implementation = mapped_test.get("test_implementation", [])
            logger.info(f"Successfully mapped {len(test_implementation)} test steps")
            
            # Execute the test steps
            logger.info("Executing test steps with executor agent")
            execution_result = await self.executor_agent.execute({"test_plan": test_implementation})
            
            if "error" in execution_result:
                logger.error(f"Failed to execute test steps: {execution_result['error']}")
                return []
                
            # Generate a report
            logger.info("Generating report with reporter agent")
            report = await self.reporter_agent.execute({
                "execution_result": execution_result,
                "parsed_test": parsed_test,
                "test_implementation": test_implementation
            })
            
            # Record end time
            end_time = time.time()
            duration_seconds = end_time - start_time
            
            # Log execution summary
            status = execution_result.get("status", "unknown")
            logger.info(f"Feature execution completed in {duration_seconds:.2f} seconds with status: {status}")
            
            # Return the results
            return [execution_result]
            
        except Exception as e:
            error_details = handle_error(e, "Feature execution failed")
            logger.error(error_details["message"], exc_info=True)
            
            # Return empty results
            return []