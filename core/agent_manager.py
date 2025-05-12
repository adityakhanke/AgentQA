"""
Agent Manager: Manages the lifecycle and interactions of AI agents.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Type, Tuple, Callable

from core.context_manager import ContextManager
from core.error_handler import handle_error
from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

class AgentManager:
    """
    Manages the lifecycle and interactions of AI agents.
    """
    
    def __init__(
        self,
        agent_config: Dict[str, Any],
        llm_config: Dict[str, Any],
        context_manager: ContextManager
    ):
        """
        Initialize the agent manager.
        
        Args:
            agent_config: Agent configuration
            llm_config: LLM configuration
            context_manager: Context manager for shared state
        """
        self.agent_config = agent_config
        self.llm_config = llm_config
        self.context_manager = context_manager
        self.agents = {}
        
    async def create_agent(
        self,
        agent_type: str,
        agent_class: Type,
        additional_params: Dict[str, Any] = None
    ) -> Any:
        """
        Create a new agent instance.
        
        Args:
            agent_type: Type of agent to create
            agent_class: Agent class
            additional_params: Additional parameters for agent initialization
            
        Returns:
            Created agent instance
        """
        try:
            # Get agent-specific configuration
            agent_specific_config = self.agent_config.get(agent_type, {})
            
            # Merge with base LLM config
            merged_llm_config = {**self.llm_config}
            
            # Override with agent-specific settings
            for key, value in agent_specific_config.items():
                if key not in ["name"]:  # Skip non-LLM settings
                    merged_llm_config[key] = value
            
            # Create the agent
            params = {
                "name": agent_specific_config.get("name", f"{agent_type.capitalize()}Agent"),
                "llm_config": merged_llm_config,
                "context_manager": self.context_manager
            }
            
            # Add additional parameters
            if additional_params:
                params.update(additional_params)
                
            # Initialize the agent
            agent = agent_class(**params)
            
            # Store the agent
            self.agents[agent_type] = agent
            
            logger.info(f"Created agent: {agent.name} ({agent_type})")
            return agent
            
        except Exception as e:
            error_details = handle_error(e, f"Failed to create agent: {agent_type}")
            logger.error(error_details["message"], exc_info=True)
            raise
            
    def get_agent(self, agent_type: str) -> Optional[Any]:
        """
        Get an agent by type.
        
        Args:
            agent_type: Type of agent to retrieve
            
        Returns:
            Agent instance or None if not found
        """
        return self.agents.get(agent_type)
        
    async def execute_agent(
        self,
        agent_type: str,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute an agent with input data.
        
        Args:
            agent_type: Type of agent to execute
            input_data: Input data for the agent
            
        Returns:
            Agent execution results
        """
        agent = self.get_agent(agent_type)
        if not agent:
            return {"error": f"Agent not found: {agent_type}"}
            
        return await agent.execute(input_data)
        
    async def execute_pipeline(
        self,
        pipeline: List[Tuple[str, Callable[[Dict[str, Any]], Dict[str, Any]]]]
    ) -> Dict[str, Any]:
        """
        Execute a pipeline of agents.
        
        Args:
            pipeline: List of (agent_type, input_transform) tuples
                agent_type: Type of agent to execute
                input_transform: Function to transform previous output to input for this agent
                
        Returns:
            Result of the last agent in the pipeline
        """
        result = {}
        
        for agent_type, input_transform in pipeline:
            # Transform input for this agent
            agent_input = input_transform(result)
            
            # Execute the agent
            result = await self.execute_agent(agent_type, agent_input)
            
            # Check for errors
            if "error" in result:
                logger.error(f"Pipeline execution failed at agent {agent_type}: {result['error']}")
                return result
                
        return result