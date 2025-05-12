"""
Base Agent: Foundation class for all specialized agents in the testing framework.
"""

from typing import Dict, Any, List, Union

from core.context_manager import ContextManager
from core.error_handler import handle_error
from utils.logger import get_logger


# Configure logger
logger = get_logger(__name__)

class BaseAgent:
    """
    Base class for all agents in the system, providing common functionality
    and integration with the context manager and error handling.
    """
    
    def __init__(
        self,
        name: str,
        llm_config: Dict[str, Any],
        context_manager: ContextManager
    ):
        """
        Initialize the base agent.
        
        Args:
            name: Agent name
            llm_config: LLM configuration
            context_manager: Context manager for shared state
        """
        self.name = name
        self.llm_config = llm_config
        self.context_manager = context_manager
        self.logger = get_logger(f"agent.{name}")
        self.llm = None
        
        # Initialize LLM
        self._init_llm()
        
    def _init_llm(self) -> None:
        """Initialize the language model client based on configuration."""
        try:
            # Import dynamically to avoid circular imports
            from LLM.llm_client import create_llm_client
            
            self.llm = create_llm_client(self.llm_config)
            self.logger.debug(f"Initialized LLM for agent: {self.name}")
        except Exception as e:
            error_details = handle_error(e, f"Failed to initialize LLM for agent: {self.name}")
            self.logger.error(error_details["message"])
            
    async def execute(self, input_data: Union[Dict[str, Any], str]) -> Dict[str, Any]:
        """
        Execute the agent's task.
        
        Args:
            input_data: Input data for the agent
            
        Returns:
            Execution results
        """
        # This method should be implemented by subclasses
        raise NotImplementedError("Subclasses must implement execute()")
    
    async def generate_response(self, prompt: Union[str, List[Dict[str, str]]]) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            prompt: Prompt for the LLM (either a string or a list of message objects)
            
        Returns:
            LLM response
        """
        if not self.llm:
            self.logger.warning(f"LLM not initialized for agent: {self.name}")
            return ""
            
        try:
            # Convert string prompt to message format if needed
            if isinstance(prompt, str):
                messages = [
                    {"role": "system", "content": f"You are the {self.name}, an AI assistant for mobile app testing."},
                    {"role": "user", "content": prompt}
                ]
            else:
                messages = prompt
                
            # Generate response from LLM
            response = await self.llm.generate_response(messages)
            return response.content
            
        except Exception as e:
            error_details = handle_error(e, "Failed to generate LLM response")
            self.logger.error(error_details["message"])
            return ""
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the shared context.
        
        Args:
            key: The context key to retrieve
            default: Default value if key not found
            
        Returns:
            The value associated with the key or the default value
        """
        return self.context_manager.get(key, default)
        
    def set_context(self, key: str, value: Any) -> None:
        """
        Set a value in the shared context.
        
        Args:
            key: The context key to set
            value: The value to store
        """
        self.context_manager.set(key, value)
        
    def log_info(self, message: str) -> None:
        """
        Log an info message.
        
        Args:
            message: Message to log
        """
        self.logger.info(message)
        
    def log_warning(self, message: str) -> None:
        """
        Log a warning message.
        
        Args:
            message: Message to log
        """
        self.logger.warning(message)
        
    def log_error(self, message: str, exc_info: bool = False) -> None:
        """
        Log an error message.
        
        Args:
            message: Message to log
            exc_info: Whether to include exception info
        """
        self.logger.error(message, exc_info=exc_info)
        
    def handle_error(self, error: Exception, message: str) -> Dict[str, Any]:
        """
        Handle an error.
        
        Args:
            error: The exception
            message: Error message
            
        Returns:
            Error details
        """
        return handle_error(error, message)