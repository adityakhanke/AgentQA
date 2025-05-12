#!/usr/bin/env python3
"""
Main entry point for the enhanced mobile testing framework.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

from agents.parser_agent import ParserAgent
from agents.implementor_agent import ImplementorAgent
from agents.executor_agent import ExecutorAgent
from agents.checker_agent import CheckerAgent
from agents.reporter_agent import ReporterAgent
from config.config_loader import load_config
from core.context_manager import ContextManager
from core.agent_manager import AgentManager
from core.context_manager import ContextManager
from core.orchestrator import TestOrchestrator
from gherkin.parser import GherkinParser
from tools.session_management import load_app, quit_driver
from tools.tool_registry import load_tools_from_modules
from utils.logger import setup_logger

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Enhanced mobile testing framework using AI agents and Appium"
    )
    
    parser.add_argument(
        "--feature", "-f", 
        required=True, 
        help="Path to Gherkin feature file or directory containing feature files"
    )
    
    parser.add_argument(
        "--config", "-c", 
        default="config/config.yaml", 
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--platform", "-p", 
        default="android", 
        choices=["android", "ios"], 
        help="Target mobile platform"
    )
    
    parser.add_argument(
        "--app", "-a", 
        help="Path to app package/bundle"
    )
    
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true", 
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "--report-dir", "-r", 
        default="test_reports", 
        help="Directory to store test reports"
    )
    
    parser.add_argument(
        "--screenshots", "-s", 
        action="store_true", 
        help="Take screenshots during test execution"
    )
    
    parser.add_argument(
        "--fail-fast", "-ff", 
        action="store_true",
        help="Stop test execution on first failure"
    )
    
    parser.add_argument(
        "--timeout", "-t", 
        type=int, 
        default=30,
        help="Default timeout in seconds for element interactions"
    )
    
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retries for failed steps"
    )

    parser.add_argument(
        "--screens_dir",
        default="user_inputs/screens/",
        help="Path to screens"
    )
    
    return parser.parse_args()

async def main():
    """Main entry point for the testing framework."""
    # Parse command-line arguments
    args = parse_arguments()
    
    # Set up logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger = setup_logger(log_level)
    logger.info("Starting enhanced mobile testing framework")
    
    try:
        # Load configuration
        config_path = os.path.abspath(args.config)
        logger.info(f"Loading configuration from: {config_path}")
        config = load_config(config_path)

         # Initialize screen registry
        from utils.screen_registry import ScreenRegistry
        screens_dir = Path(args.screens_dir) if args.screens_dir else Path("user_inputs/screens")
        screens_registry = ScreenRegistry(screens_dir)
        
        # Set global context
        ContextManager.set("config", config)
        ContextManager.set("platform", args.platform)

        # Additional context settings
        ContextManager.set("screenshot_on_step", args.screenshots)
        ContextManager.set("fail_fast", args.fail_fast)
        ContextManager.set("default_timeout", args.timeout)
        ContextManager.set("max_retries", args.retries)

        # Add screens registry to context manager
        ContextManager.set("screens_registry", screens_registry)

        # Log screen loading info
        screen_count = len(screens_registry.get_all_screens())
        logging.info(f"Loaded {screen_count} screen definitions from {screens_dir}")


        # Create report directory if it doesn't exist
        report_dir = Path(args.report_dir)
        report_dir.mkdir(exist_ok=True, parents=True)
        ContextManager.set("report_dir", str(report_dir))

        # Initialize driver for all
        ContextManager.set("driver", await load_app())

        # Create agent manager
        agent_manager = AgentManager(
            agent_config=config.get("agents", {}),
            llm_config=config.get("llm", {}),
            context_manager=ContextManager
        )
        
        # Load tools
        tool_modules = [
            "tools.session_management",
            "tools.gestures",
            "tools.interactions",
            "tools.validations",
            "tools.device_control"
        ]
        tool_count = load_tools_from_modules(tool_modules)
        logger.info(f"Loaded {tool_count} tools from {len(tool_modules)} modules")
        
        # Create agents
        parser_agent = await agent_manager.create_agent(
            "parser", 
            ParserAgent, 
            {"name": "ParserAgent"}
        )
        
        implementor_agent = await agent_manager.create_agent(
            "implementor", 
            ImplementorAgent, 
            {"name": "ImplementorAgent"}
        )

        checker_llm_config = config.get("checker_llm", config.get("llm", {}))
        
        checker_agent = await agent_manager.create_agent(
            "checker", 
            CheckerAgent,
            {"name": "CheckerAgent", "llm_config": checker_llm_config}
        )
        
        executor_agent = await agent_manager.create_agent(
            "executor", 
            ExecutorAgent, 
            {
                "name": "ExecutorAgent",
                "checker_agent": checker_agent,
                "max_retries": args.retries
            }
        )
        
        reporter_agent = await agent_manager.create_agent(
            "reporter", 
            ReporterAgent, 
            {"name": "ReporterAgent"}
        )
        
        # Initialize the test orchestrator
        orchestrator = TestOrchestrator(
            feature_path=args.feature,
            context_manager=ContextManager,
            agent_manager=agent_manager,
            parser_agent=parser_agent,
            implementor_agent=implementor_agent,
            executor_agent=executor_agent,
            reporter_agent=reporter_agent
        )
        
        # Run the tests
        results = await orchestrator.run()
        
        # Output summary
        total_scenarios = len(results)
        passed_scenarios = sum(1 for r in results if r["status"] == "pass")
        
        logger.info(f"Test execution completed: {passed_scenarios}/{total_scenarios} scenarios passed")
        
        # Return appropriate exit code
        if passed_scenarios == total_scenarios:
            return 0
        else:
            return 1
            
    except KeyboardInterrupt:
        logger.info("Test execution interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return 1
    finally:
        # Clean up
        try:
            await quit_driver()
        except:
            pass

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)