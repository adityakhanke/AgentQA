"""
Executor Agent: Executes test steps using mobile interaction tools with interrupt handling,
network monitoring, and screen validation.

This agent is responsible for executing test steps by utilizing the
registered tools based on the test plan provided by the Implementor Agent.
Enhanced with the ability to handle interruptions, monitor network activity,
and validate screens.
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional, Union

from agents.base_agent import BaseAgent
from core.context_manager import ContextManager
from core.error_handler import handle_error
from tools.session_management import load_app, page_source
from tools.interactions import element_is_displayed, single_tap, send_keys
from tools.tool_registry import get_tool_function, get_tools_for_agent
from utils.logger import get_logger
from utils.extract_json import extract_json
from utils.screenshot_manager import ScreenshotManager
from utils.network_monitor import NetworkMonitor

# Configure logger
logger = get_logger(__name__)

class ExecutorAgent(BaseAgent):
    """
    Agent responsible for executing test steps using registered tools,
    with enhanced interrupt handling capabilities based on Gherkin handlers,
    network monitoring, and screen validation.
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
        
        # Interrupt handling properties
        self.feature_interrupt_handlers = []
        self.scenario_interrupt_handlers = []
        self.interrupt_manager = None
        self.interrupts_handled = []
        
        # Get the NetworkMonitor instance
        driver = self.context_manager.get("driver")
        self.network_monitor = NetworkMonitor.get_instance(driver)

        # Store in context if not already there
        if self.network_monitor and not self.context_manager.get("network_monitor"):
            self.context_manager.set("network_monitor", self.network_monitor)
            logger.info(f"Network monitoring initialized in {self.name}")
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a test plan with interrupt handling.
        
        Args:
            input_data: Input data containing the test plan and interrupt handlers
                - test_plan: The test plan to execute
                - parsed_test: The parsed test case (for tag extraction)
                
        Returns:
            Dictionary containing the execution results
        """
        try:
            # Extract the test plan and parsed test data
            if isinstance(input_data, str):
                # Try to extract JSON from string if needed
                test_plan = extract_json(input_data)
                if not test_plan:
                    test_plan = json.loads(input_data)
                parsed_test = {}
            else:
                test_plan = input_data.get("test_plan")
                parsed_test = input_data.get("parsed_test", {})
                
            if not test_plan:
                return {"status": "error", "message": "No test plan provided"}
                
            # Initialize the execution context
            self.test_results = []
            self.current_test_case = None
            self.interrupts_handled = []
            
            # Get the interrupt manager from context
            self.interrupt_manager = self.context_manager.get("interrupt_manager")
            if not self.interrupt_manager:
                logger.warning("No interrupt manager found in context, interrupt handling will be disabled")
            
            # Extract feature-level interrupt handlers from tags
            self.feature_interrupt_handlers = []
            if self.interrupt_manager:
                feature_tags = parsed_test.get("tags", [])
                self.feature_interrupt_handlers = self.interrupt_manager.get_handlers_from_tags(feature_tags)
                logger.info(f"Loaded {len(self.feature_interrupt_handlers)} feature-level interrupt handlers")
            
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
            execution_result = await self._execute_test_plan(test_plan, parsed_test)
            
            # Add information about handled interrupts
            if self.interrupts_handled:
                execution_result["interrupts_handled"] = self.interrupts_handled
                execution_result["total_interrupts_handled"] = len(self.interrupts_handled)
            
            return execution_result
                
        except Exception as e:
            error_details = handle_error(e, "Test execution failed")
            logger.error(error_details["message"], exc_info=True)
            
            return {
                "status": "error",
                "message": error_details["message"],
                "traceback": error_details.get("traceback")
            }
            
    async def _execute_test_plan(
        self, 
        test_plan: List[Dict[str, Any]],
        parsed_test: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a test plan consisting of multiple steps.
        
        Args:
            test_plan: List of test steps to execute
            parsed_test: The parsed test case (for tag extraction)
            
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
        
        # Extract scenario information from parsed test
        scenarios = parsed_test.get("scenarios", [])
        scenario_tags_map = {}
        
        # Create mapping of step descriptions to scenario tags for interrupt handling
        for scenario in scenarios:
            scenario_tags = scenario.get("tags", [])
            for step in scenario.get("steps", []):
                step_desc = step.get("text", "")
                scenario_tags_map[step_desc] = scenario_tags
        
        # Execute each step in the test plan
        for step_num, step in enumerate(test_plan, 1):
            # Set current scenario interrupt handlers
            original_step = step.get("step", {})
            step_desc = original_step.get("description", "")
            
            # Check if this step involves a screen transition or validation
            await self._check_and_validate_screen(step_desc)
            
            # Get scenario tags for this step
            scenario_tags = scenario_tags_map.get(step_desc, [])
            if scenario_tags:
                # Extract scenario-level interrupt handlers
                if self.interrupt_manager:
                    self.scenario_interrupt_handlers = self.interrupt_manager.get_handlers_from_tags(scenario_tags)
            
            # Get step-level tags
            step_tags = original_step.get("tags", [])
            
            # Execute the step with interrupt handling
            step_result = await self._execute_step(step, step_num, step_tags)
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
    
    async def _check_and_validate_screen(self, step_description: str) -> Optional[str]:
        """
        Check if a step involves screen validation and validate if necessary.
        
        Args:
            step_description: Step description text
            
        Returns:
            Screen name if validation was performed, None otherwise
        """
        # Extract screen name from common patterns
        import re
        patterns = [
            r"I (?:am on|navigate to|go to|should see) the [\"'](.+?)[\"'] (?:screen|page)",
            r"the app (?:displays|shows|is on) the [\"'](.+?)[\"'] (?:screen|page)",
            r"I should (?:be on|see) the [\"'](.+?)[\"'] (?:screen|page)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, step_description, re.IGNORECASE)
            if match:
                screen_name = match.group(1)
                
                # Update the current screen context
                self.context_manager.set("current_screen", screen_name)
                
                # Validate the screen
                screens_registry = self.context_manager.get("screens_registry")
                if screens_registry:
                    validation = await screens_registry.validate_current_screen(screen_name)
                    if validation.get("valid", False):
                        logger.info(f"Screen validated: {screen_name} (score: {validation.get('match_score', 0):.2f})")
                    else:
                        logger.warning(f"Screen validation failed for {screen_name}: {validation.get('message', 'Unknown error')}")
                        
                return screen_name
                
        return None
            
    async def _execute_step(
        self, 
        step: Dict[str, Any],
        step_num: int,
        step_tags: List[str] = []
    ) -> Dict[str, Any]:
        """
        Execute a single test step with interrupt handling.
        
        Args:
            step: Test step to execute
            step_num: Step number for logging
            step_tags: Tags for this specific step
            
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
            "duration_seconds": 0,
            "interrupts_handled": []
        }
        
        # Determine if this is a critical interaction or verification step
        is_critical_interaction = tool_name in ["single_tap", "send_keys", "swipe", "long_press"]
        is_verification_step = tool_name in ["element_is_displayed", "get_text"]
        
        # Wait for network for critical steps
        if is_critical_interaction or is_verification_step:
            # Only wait for a short time so we don't block test execution too much
            await self.network_monitor.wait_for_network_idle(timeout=5, idle_threshold=0.3)
        
        # Extract step-specific interrupt handlers if available
        step_interrupt_handlers = []
        if self.interrupt_manager and step_tags:
            step_interrupt_handlers = self.interrupt_manager.get_handlers_from_tags(step_tags)
            logger.debug(f"Found {len(step_interrupt_handlers)} step-specific interrupt handlers")
        
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
                
                # Handle interrupts before step execution
                pre_interrupts = await self._handle_all_interrupts(step_interrupt_handlers)
                if pre_interrupts:
                    logger.info(f"Handled {len(pre_interrupts)} interrupts before step {step_num}")
                    step_result["interrupts_handled"].extend(pre_interrupts)
                    self.interrupts_handled.extend(pre_interrupts)
                
                # Execute the tool with arguments
                if isinstance(arguments, list):
                    result = await tool_func(*arguments)
                elif isinstance(arguments, dict):
                    result = await tool_func(**arguments)
                else:
                    result = await tool_func()
                
                # Handle interrupts after step execution
                post_interrupts = await self._handle_all_interrupts(step_interrupt_handlers)
                if post_interrupts:
                    logger.info(f"Handled {len(post_interrupts)} interrupts after step {step_num}")
                    step_result["interrupts_handled"].extend(post_interrupts)
                    self.interrupts_handled.extend(post_interrupts)
                
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
                        
                        # Check for interrupts that might be blocking the element
                        interrupt_check = await self._handle_all_interrupts(step_interrupt_handlers)
                        if interrupt_check:
                            logger.info(f"Handled {len(interrupt_check)} interrupts during element correction")
                            step_result["interrupts_handled"].extend(interrupt_check)
                            self.interrupts_handled.extend(interrupt_check)
                            
                            # Retry after handling interrupts
                            retry_count += 1
                            await asyncio.sleep(1)
                            continue
                        
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
                
                # Try handling interrupts that might have caused the exception
                interrupt_check = await self._handle_all_interrupts(step_interrupt_handlers)
                if interrupt_check and retry_count < max_retries:
                    logger.info(f"Handled {len(interrupt_check)} interrupts after exception")
                    step_result["interrupts_handled"].extend(interrupt_check)
                    self.interrupts_handled.extend(interrupt_check)
                    
                    # Retry after handling interrupts
                    retry_count += 1
                    await asyncio.sleep(1)
                    continue
                
                # If retry limit reached, break the loop
                if retry_count >= max_retries:
                    break
                
                # Wait before retry
                retry_count += 1
                await asyncio.sleep(1)
        
        # Wait for network if this was an action that likely triggered new requests
        if step_result["status"] == "pass" and is_critical_interaction:
            # Wait for a very short time for any triggered requests to start
            await asyncio.sleep(0.5)
            
            # Don't wait too long - just a quick check if new requests are happening
            step_result["network_active"] = await self.network_monitor.get_active_requests_count() > 0
        
        # Take screenshot after execution if configured
        if self.screenshot_manager:
            after_screenshot = self.screenshot_manager.take_screenshot(
                f"{'error' if step_result['status'] != 'pass' else 'after'}_step_{step_num}"
            )
            step_result["screenshot"] = after_screenshot
        
        return self._finalize_step_result(step_result)
    
    async def _handle_all_interrupts(self, step_handlers: List[Dict[str, Any]] = []) -> List[Dict[str, Any]]:
        """
        Check for and handle all interrupts at different levels.
        
        Args:
            step_handlers: Step-specific interrupt handlers
            
        Returns:
            List of handled interrupts
        """
        all_results = []
        
        # First check feature-level interrupts
        feature_results = await self._handle_interrupts(self.feature_interrupt_handlers)
        if feature_results:
            all_results.extend(feature_results)
            
        # Then check scenario-level interrupts
        scenario_results = await self._handle_interrupts(self.scenario_interrupt_handlers)
        if scenario_results:
            all_results.extend(scenario_results)
            
        # Finally check step-specific interrupts
        if step_handlers:
            step_results = await self._handle_interrupts(step_handlers)
            if step_results:
                all_results.extend(step_results)
                
        return all_results
    
    async def _handle_interrupts(self, handlers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Check for and handle interrupts using the provided handlers.
        
        Args:
            handlers: List of interrupt handler definitions
            
        Returns:
            List of handled interrupts
        """
        if not handlers:
            return []
            
        results = []
        
        for handler in handlers:
            handler_name = handler.get("name", "Unknown")
            detection_elements = handler.get("detection_elements", [])
            action_elements = handler.get("action_elements", [])
            
            # Check if any detection element is visible
            for element in detection_elements:
                try:
                    # Use a short timeout to check if element is visible
                    is_visible = await element_is_displayed(element, timeout=1.0)
                    
                    if is_visible.get("body", False):
                        logger.info(f"Detected interrupt: {handler_name}")
                        
                        # Take screenshot of interrupt if configured
                        if self.screenshot_manager:
                            interrupt_screenshot = self.screenshot_manager.take_screenshot(f"interrupt_{handler_name}")
                        
                        # Perform actions
                        actions_results = []
                        for action in action_elements:
                            action_type = action.get("type", "tap")
                            
                            if action_type == "tap":
                                element_id = action.get("element")
                                result = await single_tap(element_id)
                                actions_results.append(result)
                            elif action_type == "wait":
                                duration = action.get("duration", 1)
                                await asyncio.sleep(duration)
                                actions_results.append({
                                    "message": "Success", 
                                    "details": f"Waited for {duration} seconds"
                                })
                            elif action_type == "custom_tool":
                                tool_name = action.get("tool_name")
                                args = action.get("args", [])
                                
                                tool_func = get_tool_function("executor", tool_name)
                                if tool_func:
                                    result = await tool_func(*args)
                                    actions_results.append(result)
                                else:
                                    actions_results.append({
                                        "message": "Failure", 
                                        "error": f"Tool not found: {tool_name}"
                                    })
                        
                        handled_result = {
                            "name": handler_name,
                            "handler": handler,
                            "detection_element": element,
                            "time": time.time(),
                            "actions": actions_results,
                            "success": all(result.get("message") == "Success" for result in actions_results)
                        }
                        
                        results.append(handled_result)
                        
                        # After handling an interrupt, take a small pause to let the UI update
                        await asyncio.sleep(0.5)
                        break  # Move to next handler after handling this one
                except Exception as e:
                    # Log but continue checking other elements
                    logger.debug(f"Error checking for interrupt element {element}: {str(e)}")
        
        return results
    
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
            
        # Add information about interrupts if any were handled
        if step_result["interrupts_handled"]:
            interrupt_count = len(step_result["interrupts_handled"])
            logger.info(f"Handled {interrupt_count} interrupts during step {step_result['step_num']}")
            
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
            execution_results = await self._execute_test_plan(test_plan, test_case)
            
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
    
    async def _check_for_dynamic_interrupts(self) -> Optional[Dict[str, Any]]:
        """
        Use LLM to check for and identify unexpected dialogs or interrupts.
        
        Returns:
            Dictionary with interrupt information or None if no interrupts detected
        """
        # Get current page source
        page_src_result = await page_source()
        page_src = page_src_result.get("body", "")
        
        # Create prompt for LLM
        prompt = f"""
        You are an expert in mobile UI analysis.
        
        Analyze this page source and determine if there appears to be a dialog, popup,
        or interruption that might block normal test flow.
        
        Page source:
        ```xml
        {page_src[:3000]}
        ```
        
        If you detect a dialog or popup, return:
        1. The type of dialog
        2. The element IDs that would dismiss or handle it
        3. The action to perform (tap, enter text, etc.)
        
        Return your analysis as JSON with these fields:
        - is_dialog: true/false
        - dialog_type: description of the dialog
        - detection_elements: array of elements that identify this dialog
        - action_elements: array of elements to interact with
        - actions: array of actions to take (each with type and element)
        
        Return null if no dialog or popup is detected.
        """
        
        # Get response from LLM
        messages = [
            {"role": "system", "content": "You are an expert in mobile UI analysis."},
            {"role": "user", "content": prompt}
        ]
        
        response = await self.generate_response(messages)
        analysis = extract_json(response)
        
        if analysis and analysis.get("is_dialog", False):
            logger.info(f"LLM detected dialog: {analysis.get('dialog_type')}")
            
            # Try to handle the detected dialog
            detection_elements = analysis.get("detection_elements", [])
            actions = analysis.get("actions", [])
            
            # Convert LLM-suggested actions to our action format
            action_elements = []
            for action in actions:
                action_type = action.get("type", "tap")
                element = action.get("element")
                
                if action_type == "tap" and element:
                    action_elements.append({
                        "type": "tap",
                        "element": element
                    })
                elif action_type == "input" and element:
                    text = action.get("text", "")
                    action_elements.append({
                        "type": "custom_tool",
                        "tool_name": "send_keys",
                        "args": [element, text]
                    })
            
            # Create a dynamic handler
            dynamic_handler = {
                "name": f"Dynamic: {analysis.get('dialog_type', 'Unknown Dialog')}",
                "detection_elements": detection_elements,
                "action_elements": action_elements
            }
            
            # Try to handle it
            handled = await self._handle_interrupts([dynamic_handler])
            if handled:
                return {
                    "dynamic_handler": dynamic_handler,
                    "handled": handled
                }
            
        return None