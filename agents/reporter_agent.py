"""
Reporter Agent: Generates comprehensive test reports and analysis.

This agent is responsible for taking test execution results and generating
detailed reports, insights, and visualizations.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from agents.base_agent import BaseAgent
from core.context_manager import ContextManager
from core.error_handler import handle_error
from reports.test_reporter import TestReporter, create_test_reporter
from utils.logger import get_logger
from utils.extract_json import extract_json

# Configure logger
logger = get_logger(__name__)

class ReporterAgent(BaseAgent):
    """
    Agent responsible for generating comprehensive test reports and analysis.
    """
    
    def __init__(
        self,
        name: str,
        llm_config: Dict[str, Any],
        context_manager: ContextManager,
        report_dir: Optional[str] = None
    ):
        """
        Initialize the reporter agent.
        
        Args:
            name: Agent name
            llm_config: LLM configuration
            context_manager: Context manager for shared state
            report_dir: Directory to store reports (overrides context setting)
        """
        super().__init__(name, llm_config, context_manager)
        
        # Get report directory from context or parameter
        self.report_dir = report_dir or self.context_manager.get("report_dir", "test_reports")
        
        # Create reporter instance
        self.reporter = create_test_reporter(
            report_dir=self.report_dir,
            include_screenshots=self.context_manager.get("include_screenshots", True),
            include_logs=self.context_manager.get("include_logs", True),
            generate_html=self.context_manager.get("generate_html", True)
        )
        
        logger.info(f"Reporter agent initialized with output directory: {self.report_dir}")
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a report based on test execution results.
        
        Args:
            input_data: Input data containing test execution results
                - execution_result: The execution results
                - parsed_test: The parsed test (optional)
                - test_implementation: The test implementation (optional)
                
        Returns:
            Dictionary containing the report information
        """
        try:
            # Extract execution results from input data
            execution_result = input_data.get("execution_result", {})
            parsed_test = input_data.get("parsed_test", {})
            test_implementation = input_data.get("test_implementation", [])
            
            if not execution_result:
                return {"error": "No execution results provided"}
                
            # Generate the report
            report = await self._generate_report(
                execution_result, 
                parsed_test, 
                test_implementation
            )
            
            return report
            
        except Exception as e:
            error_details = handle_error(e, "Report generation failed")
            logger.error(error_details["message"], exc_info=True)
            
            return {"error": error_details["message"]}
    
    async def _generate_report(
        self, 
        execution_result: Dict[str, Any],
        parsed_test: Dict[str, Any],
        test_implementation: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive test report.
        
        Args:
            execution_result: Test execution results
            parsed_test: Parsed test information
            test_implementation: Test implementation details
            
        Returns:
            Report information
        """
        try:
            # Create a new report if needed
            if not hasattr(self, 'reporter') or self.reporter is None:
                self.reporter = create_test_reporter(
                    report_dir=self.report_dir,
                    include_screenshots=self.context_manager.get("include_screenshots", True),
                    include_logs=self.context_manager.get("include_logs", True),
                    generate_html=self.context_manager.get("generate_html", True)
                )
                
            # Enrich execution result with feature and scenario info from parsed test
            if parsed_test:
                enriched_result = execution_result.copy()
                enriched_result["feature"] = parsed_test.get("feature", {})
                enriched_result["scenario"] = parsed_test.get("scenario", {})
                execution_result = enriched_result
                
            # Add execution result to the report
            self.reporter.add_test_result(execution_result)
            
            # Add screenshots if available
            screenshots = execution_result.get("screenshots", [])
            for screenshot in screenshots:
                if isinstance(screenshot, str):
                    self.reporter.add_screenshot(screenshot)
                elif isinstance(screenshot, dict) and "path" in screenshot:
                    self.reporter.add_screenshot(
                        screenshot["path"], 
                        screenshot.get("description", None)
                    )
                    
            # Finalize the report
            report_data = self.reporter.finalize_report()
            
            # Generate insights using LLM if enabled
            if self.context_manager.get("generate_insights", False):
                insights = await self._generate_insights(
                    execution_result, 
                    parsed_test,
                    report_data
                )
                report_data["insights"] = insights
                
            return {
                "report": report_data,
                "report_path": self.reporter._save_json_report(),
                "html_report_path": self.reporter._generate_html_report() if self.reporter.generate_html else None
            }
            
        except Exception as e:
            error_details = handle_error(e, "Report generation failed")
            logger.error(error_details["message"])
            return {"error": error_details["message"]}
    
    async def _generate_insights(
        self,
        execution_result: Dict[str, Any],
        parsed_test: Dict[str, Any],
        report_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate insights and recommendations using LLM.
        
        Args:
            execution_result: Test execution results
            parsed_test: Parsed test information
            report_data: Generated report data
            
        Returns:
            Dictionary of insights and recommendations
        """
        try:
            # Create a prompt for the LLM to analyze the results
            prompt = self._create_insights_prompt(
                execution_result, 
                parsed_test,
                report_data
            )
            
            # Get LLM response
            llm_response = await self.generate_response(prompt)
            
            # Extract JSON from response
            insights = extract_json(llm_response)
            
            if not insights:
                # If no JSON found, try to structure the response
                insights = {
                    "summary": llm_response[:300],  # Use first part as summary
                    "detailed_analysis": llm_response,
                    "recommendations": []
                }
                
            logger.info("Generated test insights using LLM")
            return insights
            
        except Exception as e:
            logger.warning(f"Failed to generate insights: {str(e)}")
            return {
                "error": f"Failed to generate insights: {str(e)}"
            }
    
    def _create_insights_prompt(
        self,
        execution_result: Dict[str, Any],
        parsed_test: Dict[str, Any],
        report_data: Dict[str, Any]
    ) -> str:
        """
        Create a prompt for the LLM to generate insights.
        
        Args:
            execution_result: Test execution results
            parsed_test: Parsed test information
            report_data: Generated report data
            
        Returns:
            Formatted prompt
        """
        # Extract key metrics
        summary = report_data.get("summary", {})
        metrics = report_data.get("metrics", {})
        
        total_tests = summary.get("total_tests", 0)
        passed_tests = summary.get("passed_tests", 0)
        failed_tests = summary.get("failed_tests", 0)
        total_steps = summary.get("total_steps", 0)
        passed_steps = summary.get("passed_steps", 0)
        failed_steps = summary.get("failed_steps", 0)
        
        test_pass_percentage = metrics.get("test_pass_percentage", 0)
        step_pass_percentage = metrics.get("step_pass_percentage", 0)
        
        # Extract failed steps for analysis
        failed_step_details = []
        for test in report_data.get("tests", []):
            for step in test.get("steps", []):
                if step.get("status", "") == "fail":
                    failed_step_details.append({
                        "description": step.get("description", ""),
                        "error": step.get("error", ""),
                        "message": step.get("message", "")
                    })
        
        # Create the prompt
        prompt = f"""
        You are an expert test analyst. Analyze the following mobile test execution results and provide insights, patterns, and recommendations.
        
        # Test Execution Summary
        - Total Tests: {total_tests}
        - Passed Tests: {passed_tests} ({test_pass_percentage:.1f}%)
        - Failed Tests: {failed_tests}
        - Total Steps: {total_steps}
        - Passed Steps: {passed_steps} ({step_pass_percentage:.1f}%)
        - Failed Steps: {failed_steps}
        
        # Failed Step Details
        {json.dumps(failed_step_details, indent=2)}
        
        # Feature Information
        {json.dumps(parsed_test.get("feature", {}), indent=2)}
        
        # Scenario Information
        {json.dumps(parsed_test.get("scenario", {}), indent=2)}
        
        Please analyze the test results and provide:
        1. A concise summary of the test execution
        2. Detailed analysis of any patterns in failures
        3. Potential root causes for failures
        4. Recommendations for improving test reliability
        5. Suggestions for improving the application under test
        
        Return your analysis in JSON format with these keys:
        - summary: A concise summary (1-2 sentences)
        - detailed_analysis: Detailed analysis of patterns and issues
        - potential_root_causes: List of potential root causes
        - recommendations: List of recommendations for improving tests
        - app_suggestions: Suggestions for improving the application
        
        Example response format:
        ```json
        {
          "summary": "The test execution showed moderate success with 75% of tests passing, but revealed consistent UI element identification issues.",
          "detailed_analysis": "The failures primarily occurred during interaction with dropdown elements and form submissions...",
          "potential_root_causes": [
            "Inconsistent element IDs across app versions",
            "Timing issues with dynamic content loading"
          ],
          "recommendations": [
            "Use more robust element locators combining multiple attributes",
            "Add explicit waits for dynamic content loading"
          ],
          "app_suggestions": [
            "Standardize element IDs across the application",
            "Improve loading state indicators"
          ]
        }
        ```
        
        Only return the JSON without any explanation.
        """
        
        return prompt
        
    async def generate_report_for_test_results(
        self,
        test_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate a consolidated report for multiple test results.
        
        Args:
            test_results: List of test results
            
        Returns:
            Dictionary containing the consolidated report information
        """
        try:
            # Create a new reporter for the consolidated report
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_name = f"consolidated_report_{timestamp}"
            
            consolidated_reporter = create_test_reporter(
                report_dir=self.report_dir,
                include_screenshots=self.context_manager.get("include_screenshots", True),
                include_logs=self.context_manager.get("include_logs", True),
                generate_html=self.context_manager.get("generate_html", True),
                report_name=report_name
            )
            
            # Add each test result to the report
            for test_result in test_results:
                consolidated_reporter.add_test_result(test_result)
                
                # Add screenshots if available
                screenshots = test_result.get("screenshots", [])
                for screenshot in screenshots:
                    if isinstance(screenshot, str):
                        consolidated_reporter.add_screenshot(screenshot)
                    elif isinstance(screenshot, dict) and "path" in screenshot:
                        consolidated_reporter.add_screenshot(
                            screenshot["path"], 
                            screenshot.get("description", None)
                        )
                        
            # Finalize the report
            report_data = consolidated_reporter.finalize_report()
            
            return {
                "report": report_data,
                "report_path": consolidated_reporter._save_json_report(),
                "html_report_path": consolidated_reporter._generate_html_report() if consolidated_reporter.generate_html else None
            }
            
        except Exception as e:
            error_details = handle_error(e, "Consolidated report generation failed")
            logger.error(error_details["message"])
            return {"error": error_details["message"]}
    
    async def generate_trend_analysis(
        self,
        report_files: List[str],
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate trend analysis from multiple report files.
        
        Args:
            report_files: List of report file paths to analyze
            output_file: Optional output file path for the trend analysis
            
        Returns:
            Dictionary containing the trend analysis
        """
        try:
            # Load reports
            reports = []
            for report_file in report_files:
                try:
                    with open(report_file, 'r', encoding='utf-8') as f:
                        report_data = json.load(f)
                        reports.append(report_data)
                except Exception as e:
                    logger.warning(f"Failed to load report file {report_file}: {str(e)}")
                    
            if not reports:
                return {"error": "No valid report files found"}
                
            # Extract metrics and trends
            trend_data = {
                "dates": [],
                "pass_rates": [],
                "test_counts": [],
                "avg_durations": [],
                "failing_components": {}
            }
            
            for report in reports:
                # Extract timestamp
                timestamp = report.get("timestamp", "")
                if timestamp:
                    # Convert to date only
                    date = timestamp.split("T")[0] if "T" in timestamp else timestamp
                    trend_data["dates"].append(date)
                    
                # Extract summary metrics
                summary = report.get("summary", {})
                total_tests = summary.get("total_tests", 0)
                passed_tests = summary.get("passed_tests", 0)
                
                if total_tests > 0:
                    pass_rate = (passed_tests / total_tests) * 100
                else:
                    pass_rate = 0
                    
                trend_data["pass_rates"].append(pass_rate)
                trend_data["test_counts"].append(total_tests)
                
                # Extract duration
                execution_time = report.get("execution_time", 0)
                trend_data["avg_durations"].append(execution_time)
                
                # Extract failing components
                for test in report.get("tests", []):
                    for step in test.get("steps", []):
                        if step.get("status", "") == "fail":
                            component = step.get("element", "unknown")
                            if component in trend_data["failing_components"]:
                                trend_data["failing_components"][component] += 1
                            else:
                                trend_data["failing_components"][component] = 1
                                
            # Sort failing components by count
            sorted_components = sorted(
                trend_data["failing_components"].items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            trend_data["failing_components"] = [
                {"name": name, "failures": count}
                for name, count in sorted_components[:10]  # Top 10 failing components
            ]
            
            # Calculate overall metrics
            if trend_data["pass_rates"]:
                trend_data["avg_pass_rate"] = sum(trend_data["pass_rates"]) / len(trend_data["pass_rates"])
                trend_data["pass_rate_trend"] = trend_data["pass_rates"][-1] - trend_data["pass_rates"][0] if len(trend_data["pass_rates"]) > 1 else 0
            else:
                trend_data["avg_pass_rate"] = 0
                trend_data["pass_rate_trend"] = 0
                
            if trend_data["avg_durations"]:
                trend_data["avg_duration"] = sum(trend_data["avg_durations"]) / len(trend_data["avg_durations"])
                trend_data["duration_trend"] = trend_data["avg_durations"][-1] - trend_data["avg_durations"][0] if len(trend_data["avg_durations"]) > 1 else 0
            else:
                trend_data["avg_duration"] = 0
                trend_data["duration_trend"] = 0
                
            # Save trend analysis if output file specified
            if output_file:
                output_path = Path(output_file)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(trend_data, f, indent=2)
                    
                logger.info(f"Trend analysis saved to: {output_file}")
                
            return {"trend_analysis": trend_data}
            
        except Exception as e:
            error_details = handle_error(e, "Trend analysis failed")
            logger.error(error_details["message"])
            return {"error": error_details["message"]}