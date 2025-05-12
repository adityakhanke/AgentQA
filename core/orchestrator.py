"""
Test Orchestrator: Coordinates the test execution process with enhanced interrupt handling.

This module provides a coordinator for the entire test execution process, integrating
the interrupt handling system for managing conditional UI elements, screen definitions,
and network monitoring for enhanced reliability.
"""

import re
import time
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from core.agent_manager import AgentManager
from core.context_manager import ContextManager
from core.error_handler import handle_error
from gherkin.parser import GherkinParser
from tools.session_management import load_app, quit_driver
from utils.logger import get_logger
from utils.network_monitor import NetworkMonitor
from gherkin.interrupt_manager import InterruptManager

# Configure logger
logger = get_logger(__name__)

class TestOrchestrator:
    """
    Orchestrates the test execution process by coordinating between agents,
    with enhanced support for interrupt handling, screen validation, and network monitoring.
    """
    
    def __init__(
        self,
        feature_path: Union[str, Path],
        context_manager: ContextManager,
        agent_manager: AgentManager,
        parser_agent,
        implementor_agent,
        executor_agent,
        reporter_agent,
        interrupt_handlers_dir: Optional[Union[str, Path]] = None
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
            interrupt_handlers_dir: Directory containing interrupt handler definitions
        """
        self.feature_path = Path(feature_path)
        self.context_manager = context_manager
        self.agent_manager = agent_manager
        self.parser_agent = parser_agent
        self.implementor_agent = implementor_agent
        self.executor_agent = executor_agent
        self.reporter_agent = reporter_agent
        self.gherkin_parser = GherkinParser()
        
        # Initialize interrupt handling
        self.interrupt_handlers_dir = Path(interrupt_handlers_dir) if interrupt_handlers_dir else None
        self.interrupt_manager = None
        
        if self.interrupt_handlers_dir and self.interrupt_handlers_dir.exists():
            self.interrupt_manager = InterruptManager(context_manager)
            self.context_manager.set("interrupt_manager", self.interrupt_manager)
            
            # Load interrupt handlers
            self.interrupt_manager.load_handlers_from_directory(str(self.interrupt_handlers_dir))
            logger.info(f"Loaded interrupt handlers from {self.interrupt_handlers_dir}")
        
        # Network monitoring initialization
        self.network_monitor = None
        
        # Detect CI environment
        self.is_ci = os.environ.get('CI', 'false').lower() == 'true'
        
        # Set appropriate timeouts based on environment
        if self.is_ci:
            self.context_manager.set("default_timeout", 15)  # shorter timeouts in CI
            self.context_manager.set("network_idle_timeout", 10)
            self.context_manager.set("max_retries", 2)  # fewer retries in CI
        else:
            self.context_manager.set("default_timeout", 30)
            self.context_manager.set("network_idle_timeout", 20) 
            self.context_manager.set("max_retries", 3)
        
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
            driver = session_result["driver"]
            self.context_manager.set("driver", driver)
            
            # Initialize network monitoring
            self.network_monitor = NetworkMonitor.get_instance(driver)
            if self.network_monitor:
                self.context_manager.set("network_monitor", self.network_monitor)
                logger.info("Network monitoring initialized successfully")

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
            await self._cleanup_resources()
    
    async def _cleanup_resources(self):
        """Clean up all resources to prevent orphaned processes in CI."""
        try:
            # Stop network monitoring if active
            if self.network_monitor:
                self.network_monitor = None
                
            # Quit driver session
            await quit_driver()
            
            # Clean up temporary files in CI
            if self.is_ci:
                for pattern in ["*.tmp", "*.log"]:
                    for file in Path(".").glob(pattern):
                        try:
                            file.unlink()
                        except:
                            pass
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
    
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
        Execute a single feature with interrupt handling and network monitoring support.
        
        Args:
            feature_content: Gherkin feature content
            
        Returns:
            List of test results
        """
        try:
            # Record start time
            start_time = time.time()
            
            # Extract feature-level tags for interrupt handling
            feature_tags = self._extract_feature_tags(feature_content)
            logger.debug(f"Feature tags: {feature_tags}")
            
            # Parse the feature using the parser agent
            logger.info("Parsing feature with parser agent")
            parsed_test = await self.parser_agent.execute({"test_case": feature_content})
            
            # Add feature tags if not already included
            if "tags" not in parsed_test:
                parsed_test["tags"] = feature_tags
            
            if "error" in parsed_test:
                logger.error(f"Failed to parse feature: {parsed_test['error']}")
                return []

            logger.info(f"Successfully parsed feature: {parsed_test.get('feature', 'Unknown')}")
            
            # Extract scenario-level tags for interrupt handling
            if "scenarios" in parsed_test:
                for scenario in parsed_test["scenarios"]:
                    # Process steps to add step-level tags for interrupt handling
                    if "steps" in scenario:
                        for step in scenario["steps"]:
                            step_tags = self._extract_step_tags(step.get("text", ""))
                            if step_tags:
                                step["tags"] = step_tags

            # Map the test steps to executable commands
            logger.info("Mapping test steps with implementor agent")
            mapped_test = await self.implementor_agent.execute({"parsed_test": parsed_test})

            if "error" in mapped_test:
                logger.error(f"Failed to map test steps: {mapped_test['error']}")
                return []
                
            test_implementation = mapped_test.get("test_implementation", [])
            logger.info(f"Successfully mapped {len(test_implementation)} test steps")
            
            # Augment test plan with tag information for interrupt handling
            augmented_test_plan = self._augment_test_plan_with_tags(test_implementation, parsed_test)
            
            # Execute the test steps with interrupt handling and network monitoring
            logger.info("Executing test steps with executor agent")
            execution_result = await self.executor_agent.execute({
                "test_plan": augmented_test_plan,
                "parsed_test": parsed_test
            })
            
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
            
            # Log information about handled interrupts
            interrupts_handled = execution_result.get("interrupts_handled", [])
            if interrupts_handled:
                logger.info(f"Handled {len(interrupts_handled)} interrupts during test execution")
                
                # Group interrupts by type
                interrupt_types = {}
                for interrupt in interrupts_handled:
                    name = interrupt.get("name", "Unknown")
                    if name in interrupt_types:
                        interrupt_types[name] += 1
                    else:
                        interrupt_types[name] = 1
                        
                # Log summary of interrupt types
                for name, count in interrupt_types.items():
                    logger.info(f"  - {name}: {count} occurrences")
            
            # Return the results
            return [execution_result]
            
        except Exception as e:
            error_details = handle_error(e, "Feature execution failed")
            logger.error(error_details["message"], exc_info=True)
            
            # Return empty results
            return []
    
    def _extract_feature_tags(self, feature_content: str) -> List[str]:
        """
        Extract tags from feature content.
        
        Args:
            feature_content: Gherkin feature content
            
        Returns:
            List of feature tags
        """
        tags = []
        tag_pattern = r'(@\w+(?::[^\s]+)?)'
        
        # Get feature line
        feature_index = feature_content.find("Feature:")
        if feature_index == -1:
            return tags
            
        # Get content before feature line
        pre_feature_content = feature_content[:feature_index].strip()
        
        # Extract tags
        found_tags = re.findall(tag_pattern, pre_feature_content)
        if found_tags:
            tags.extend(found_tags)
            
        return tags
    
    def _extract_scenario_tags(self, scenario_content: str) -> List[str]:
        """
        Extract tags from scenario content.
        
        Args:
            scenario_content: Gherkin scenario content
            
        Returns:
            List of scenario tags
        """
        tags = []
        tag_pattern = r'(@\w+(?::[^\s]+)?)'
        
        # Get scenario line
        scenario_index = scenario_content.find("Scenario:")
        if scenario_index == -1:
            scenario_index = scenario_content.find("Scenario Outline:")
            if scenario_index == -1:
                return tags
                
        # Get content before scenario line
        pre_scenario_content = scenario_content[:scenario_index].strip()
        
        # Extract tags
        found_tags = re.findall(tag_pattern, pre_scenario_content)
        if found_tags:
            tags.extend(found_tags)
            
        return tags
    
    def _extract_step_tags(self, step_content: str) -> List[str]:
        """
        Extract tags from step content.
        
        Args:
            step_content: Gherkin step content
            
        Returns:
            List of step tags
        """
        tags = []
        tag_pattern = r'@CheckInterrupts:([^\s]+)'
        
        # Extract CheckInterrupts tags
        found_tags = re.findall(tag_pattern, step_content)
        if found_tags:
            for tag in found_tags:
                interrupt_names = tag.split(',')
                for name in interrupt_names:
                    tags.append(f"@CheckInterrupts:{name.strip()}")
            
        return tags
    
    def _augment_test_plan_with_tags(
        self, 
        test_plan: List[Dict[str, Any]], 
        parsed_test: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Add tag information to the test plan for interrupt handling.
        
        Args:
            test_plan: Test plan to augment
            parsed_test: Parsed test containing tag information
            
        Returns:
            Augmented test plan
        """
        # Get feature tags
        feature_tags = parsed_test.get("tags", [])
        
        # Extract scenario and step tags
        scenarios = parsed_test.get("scenarios", [])
        
        # Map step descriptions to tags
        step_tags_map = {}
        
        for scenario in scenarios:
            scenario_tags = scenario.get("tags", [])
            
            for step in scenario.get("steps", []):
                step_text = step.get("text", "")
                step_tags = step.get("tags", [])
                
                # Combine with scenario tags
                combined_tags = scenario_tags + step_tags
                
                if combined_tags:
                    step_tags_map[step_text] = combined_tags
        
        # Augment test plan with tags
        for step in test_plan:
            original_step = step.get("step", {})
            step_desc = original_step.get("description", "")
            
            # Get tags for this step
            if step_desc in step_tags_map:
                step["tags"] = step_tags_map[step_desc]
                
            # Add feature tags to all steps
            if "tags" not in step:
                step["tags"] = []
                
            step["tags"].extend(feature_tags)

            # Check for screen context
            screen_name = self._extract_screen_reference(step_desc)
            if screen_name:
                step["screen_reference"] = screen_name
                
        return test_plan
    
    def _extract_screen_reference(self, step_text: str) -> Optional[str]:
        """
        Extract screen reference from step text.
        
        Args:
            step_text: Step text to extract from
            
        Returns:
            Screen name if found, None otherwise
        """
        # Check for common patterns that indicate screen references
        patterns = [
            r'(?:I am on|navigate to|go to|should see) the ["\'](.+?)["\'] (?:screen|page)',
            r'(?:the app displays|shows|is on) the ["\'](.+?)["\'] (?:screen|page)',
            r'(?:I should be on|see) the ["\'](.+?)["\'] (?:screen|page)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, step_text, re.IGNORECASE)
            if match:
                return match.group(1)
                
        return None
        
    def _get_handlers_for_test(self, parsed_test: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get interrupt handlers for a test based on tags.
        
        Args:
            parsed_test: Parsed test containing tag information
            
        Returns:
            Dictionary mapping levels to handler lists
        """
        if not self.interrupt_manager:
            return {
                "feature": [],
                "scenario": {},
                "step": {}
            }
            
        # Get feature-level handlers
        feature_tags = parsed_test.get("tags", [])
        feature_handlers = self.interrupt_manager.get_handlers_from_tags(feature_tags)
        
        # Get scenario-level handlers
        scenario_handlers = {}
        
        for scenario in parsed_test.get("scenarios", []):
            scenario_name = scenario.get("name", "Unknown Scenario")
            scenario_tags = scenario.get("tags", [])
            
            scenario_handlers[scenario_name] = self.interrupt_manager.get_handlers_from_tags(scenario_tags)
        
        # Get step-level handlers
        step_handlers = {}
        
        for scenario in parsed_test.get("scenarios", []):
            for step in scenario.get("steps", []):
                step_text = step.get("text", "")
                step_tags = step.get("tags", [])
                
                if step_tags:
                    step_handlers[step_text] = self.interrupt_manager.get_handlers_from_tags(step_tags)
        
        return {
            "feature": feature_handlers,
            "scenario": scenario_handlers,
            "step": step_handlers
        }