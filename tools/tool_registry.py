"""
Tool Registry: Centralized registry for all mobile testing tools.

This module provides a decorator-based registration system for mobile testing
tools, making them discoverable and accessible to the testing agents.
"""

import functools
import inspect
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Set, TypeVar, Optional, Union

logger = logging.getLogger(__name__)

# Type for tool functions
ToolFunc = TypeVar('ToolFunc', bound=Callable[..., Any])

# Global registry to store tools by category and agent
tool_registry = defaultdict(dict)

def tool(
    agent_names: List[str],
    description: str,
    name: Optional[str] = None,
    parameters: Dict[str, Any] = None,
    output: Dict[str, Any] = None
) -> Callable[[ToolFunc], ToolFunc]:
    """
    Decorator for registering tools under specific agent categories.
    
    Args:
        agent_names: List of agent names that can use this tool
        description: Description of the tool's functionality
        name: Optional name for the tool, defaults to function name
        parameters: Description of the tool's parameters
        output: Description of the tool's output
        
    Returns:
        Decorated function with tool metadata
    """
    if parameters is None:
        parameters = {}
        
    if output is None:
        output = {}
    
    def decorator(func: ToolFunc) -> ToolFunc:
        tool_name = name or func.__name__
        sig = inspect.signature(func)
        
        # Auto-generate parameters if not provided
        if not parameters and len(sig.parameters) > 0:
            auto_params = {}
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                    
                param_type = 'string'
                if param.annotation != inspect.Parameter.empty:
                    if param.annotation == str:
                        param_type = 'string'
                    elif param.annotation == int:
                        param_type = 'integer'
                    elif param.annotation == float:
                        param_type = 'number'
                    elif param.annotation == bool:
                        param_type = 'boolean'
                    else:
                        param_type = str(param.annotation)
                
                auto_params[param_name] = {
                    'type': param_type,
                    'description': f'Parameter {param_name} for {tool_name}'
                }
                
                # Handle default values
                if param.default != inspect.Parameter.empty:
                    auto_params[param_name]['default'] = param.default
            
            tool_parameters = auto_params
        else:
            tool_parameters = parameters
        
        # Auto-generate output if not provided
        if not output and sig.return_annotation != inspect.Signature.empty:
            tool_output = {
                'type': str(sig.return_annotation),
                'description': f'Output of {tool_name}'
            }
        else:
            tool_output = output
            
        # Create tool metadata
        tool_metadata = {
            'name': tool_name,
            'description': description,
            'parameters': tool_parameters,
            'output': tool_output,
            'function': func
        }
        
        # Store the tool in the registry
        for agent_name in agent_names:
            tool_registry[agent_name][tool_name] = tool_metadata
            logger.debug(f"Registered tool '{tool_name}' for agent '{agent_name}'")
        
        # Store metadata on the function itself
        func.__tool_metadata__ = tool_metadata
        
        # Return the original function unchanged
        return func
    
    return decorator

def get_tools_for_agent(agent_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Get all tools available for a specific agent.
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Dictionary of tools available for the agent
    """
    return tool_registry.get(agent_name, {})

def get_tool_metadata(agent_name: str, tool_name: str) -> Optional[Dict[str, Any]]:
    """
    Get metadata for a specific tool.
    
    Args:
        agent_name: Name of the agent
        tool_name: Name of the tool
        
    Returns:
        Tool metadata or None if not found
    """
    return tool_registry.get(agent_name, {}).get(tool_name)

def get_tool_function(agent_name: str, tool_name: str) -> Optional[Callable]:
    """
    Get the function for a specific tool.
    
    Args:
        agent_name: Name of the agent
        tool_name: Name of the tool
        
    Returns:
        Tool function or None if not found
    """
    tool_info = get_tool_metadata(agent_name, tool_name)
    if tool_info:
        return tool_info.get('function')
    return None

def list_available_tools(agent_name: Optional[str] = None) -> Dict[str, List[str]]:
    """
    List all available tools, optionally filtered by agent.
    
    Args:
        agent_name: Optional agent name to filter by
        
    Returns:
        Dictionary mapping agent names to lists of tool names
    """
    if agent_name:
        return {agent_name: list(tool_registry.get(agent_name, {}).keys())}
    
    return {agent: list(tools.keys()) for agent, tools in tool_registry.items()}

def get_tools_metadata_by_agent_name(agent_name: str) -> List[Dict[str, Any]]:
    """
    Get metadata for all tools available for a specific agent.
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        List of tool metadata dictionaries
    """
    tools = get_tools_for_agent(agent_name)
    return [
        {
            "Tool Name": tool_data["name"],
            "Description": tool_data["description"],
            "Parameters": tool_data["parameters"],
            "Output": tool_data["output"]
        }
        for tool_data in tools.values()
    ]

def load_tools_from_modules(modules: List[str], agent_name: Optional[str] = None) -> int:
    """
    Dynamically load tools from specified modules.
    
    Args:
        modules: List of module names to import
        agent_name: Optional agent name to filter by
        
    Returns:
        Number of tools loaded
    """
    import importlib
    
    tool_count = 0
    
    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
            
            # Count tools that were loaded
            if agent_name:
                tool_count += len(get_tools_for_agent(agent_name))
            else:
                tool_count += sum(len(tools) for tools in tool_registry.values())
                
            logger.info(f"Loaded tools from module: {module_name}")
        except ImportError as e:
            logger.error(f"Failed to import module '{module_name}': {e}")
    
    return tool_count