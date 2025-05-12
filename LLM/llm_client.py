"""
LLM Client: Provides a unified interface for different LLM providers.
"""

from typing import Dict, Any, List, NamedTuple

from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

class LLMResponse(NamedTuple):
    """Response from an LLM."""
    content: str
    model: str
    usage: Dict[str, int]


class LLMClient:
    """
    Abstract base class for LLM clients.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the LLM client.

        Args:
            config: LLM configuration
        """
        self.config = config

    async def generate_response(self, messages: List[Dict[str, str]]) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            messages: List of message objects

        Returns:
            Generated response
        """
        raise NotImplementedError("Subclasses must implement generate_response()")


class CustomClient(LLMClient):
    """
    Client for custom LLMs using autogen 0.4.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Custom client using autogen 0.4.

        Args:
            config: Configuration for the model
        """
        super().__init__(config)
        self.model = config.get("model", "deepseek-r1-distill-qwen-32b")
        self.api_base = config.get("api_base", "http://127.0.0.1:1234/v1")
        self.temperature = config.get("temperature", 0.1)
        self.max_tokens = config.get("max_tokens", 50000)

        # Import required autogen components
        try:
            from autogen_ext.models.openai import OpenAIChatCompletionClient
            from autogen_agentchat.agents import AssistantAgent
            from autogen_agentchat.messages import TextMessage
            from autogen_core import CancellationToken

            # Import tiktoken for token counting if available
            try:
                import tiktoken
                self.tiktoken_available = True
                self.encoding = tiktoken.get_encoding("cl100k_base")  # OpenAI's default encoding
            except ImportError:
                logger.warning("tiktoken not available, token usage will be estimated")
                self.tiktoken_available = False
                self.encoding = None

            # Store these classes for later use
            self.TextMessage = TextMessage
            self.CancellationToken = CancellationToken

            # Create the model client
            # self.model_client = OpenAIChatCompletionClient(
            #     model=self.model,
            #     api_key="NotRequiredSinceWeAreLocal",
            #     base_url=self.api_base,
            #     model_capabilities={
            #         "json_output": True,
            #         "vision": False,
            #         "function_calling": True,
            #     },
            #     temperature=self.temperature,
            #     seed=42,
            #     max_tokens=self.max_tokens
            # )


            self.model_client = OpenAIChatCompletionClient(
                model=self.model,
                api_key="NotRequiredSinceWeAreLocal",
                base_url=self.api_base,
                model_capabilities={
                    "json_output": True,
                    "vision": False,
                    "function_calling": True,
                },
                temperature=self.temperature,
                seed=42,
                max_tokens=self.max_tokens
            )

            # Create an assistant agent
            self.assistant = AssistantAgent(
                name="LLMAssistant",
                model_client=self.model_client,
                system_message="You are a helpful AI assistant."
            )

        except ImportError as e:
            logger.error(f"Failed to import required libraries from autogen 0.4: {str(e)}")
            self.model_client = None
            self.assistant = None
            self.TextMessage = None
            self.CancellationToken = None
            self.tiktoken_available = False
            self.encoding = None

    def _count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in a text string.
        
        Args:
            text: The text to count tokens for
            
        Returns:
            Number of tokens
        """
        if self.tiktoken_available and self.encoding:
            # Use tiktoken for accurate token counting
            return len(self.encoding.encode(text))
        else:
            # Fallback to a rough estimation (4 characters ≈ 1 token)
            return max(1, len(text) // 4)

    async def generate_response(self, messages: List[Dict[str, str]]) -> LLMResponse:
        """
        Generate a response using autogen 0.4.

        Args:
            messages: List of message objects

        Returns:
            Generated response
        """
        if not self.assistant:
            logger.error("Autogen assistant not initialized")
            return LLMResponse(content="Error: Autogen assistant not initialized", model=self.model, usage={})

        try:
            # Extract system message if present
            system_message = None
            for message in messages:
                if message["role"] == "system":
                    system_message = message["content"]
                    break

            # Convert messages to format expected by autogen
            # We only use the last user message for simplicity
            user_messages = [msg for msg in messages if msg["role"] == "user"]
            if not user_messages:
                # If no user message, return an error
                return LLMResponse(content="Error: No user message provided", model=self.model, usage={})
            
            # Use the last user message
            user_message = user_messages[-1]["content"]
            
            # Track token usage - compute prompt tokens
            prompt_tokens = 0
            for message in messages:
                prompt_tokens += self._count_tokens(message["content"])
            
            # Generate response using autogen's on_messages method
            response = await self.assistant.on_messages(
                [self.TextMessage(content=user_message, source="user")],
                cancellation_token=self.CancellationToken()
            )
            
            # Extract content from the response
            if hasattr(response, "text"):
                content = response.text
            elif hasattr(response, "chat_message"):
                content = response.chat_message.content
            else:
                content = str(response)
            
            # Track token usage - compute completion tokens
            completion_tokens = self._count_tokens(content)
            
            # Get the metadata from the model_client if available
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
            
            # Try to get the actual usage from the model response metadata if available
            try:
                # Check if we can access the raw response or usage info
                if hasattr(self.model_client, "last_response") and hasattr(self.model_client.last_response, "usage"):
                    # Extract usage from the last response
                    response_usage = self.model_client.last_response.usage
                    usage = {
                        "prompt_tokens": response_usage.prompt_tokens,
                        "completion_tokens": response_usage.completion_tokens,
                        "total_tokens": response_usage.total_tokens
                    }
                # Check if usage info is in the assistant's metadata
                elif hasattr(response, "metadata") and "usage" in response.metadata:
                    usage = response.metadata["usage"]
                # Check if usage is directly on the assistant
                elif hasattr(self.assistant, "usage") and self.assistant.usage:
                    usage = self.assistant.usage
                # Try to get usage from the response object
                elif hasattr(response, "usage"):
                    usage = response.usage
            except Exception as e:
                logger.warning(f"Could not extract exact usage information: {str(e)}")
                
            logger.info(f"Usage - Prompt tokens: {usage['prompt_tokens']}, " + 
                       f"Completion tokens: {usage['completion_tokens']}, " +
                       f"Total tokens: {usage['total_tokens']}")

            return LLMResponse(content=content, model=self.model, usage=usage)

        except Exception as e:
            error_msg = f"Error generating response using autogen: {str(e)}"
            logger.error(error_msg)
            return LLMResponse(content=f"Error: {error_msg}", model=self.model, usage={})




def create_llm_client(config: Dict[str, Any]) -> LLMClient:
    """
    Create an LLM client based on configuration.

    Args:
        config: LLM configuration

    Returns:
        LLM client instance
    """
    # Get the LLM provider from config
    provider_configs = config.get("config_list", [])
    # if not provider_configs:
    #     logger.warning("No LLM provider configurations found")
    #     # Default to OpenAI if no config provided
    #     return OpenAIClient({"model": "gpt-4"})

    # # Use the first provider in the list
    provider_config = provider_configs[0]

    # api_type = provider_config.get("api_type", "").lower()

    # # Create the appropriate client based on provider type
    # if api_type == "openai":
    #     return OpenAIClient(provider_config)
    # elif api_type == "anthropic":
    #     return AnthropicClient(provider_config)
    # else:
    #     logger.warning(f"Unknown LLM provider type: {api_type}, defaulting to OpenAI")
    #     return OpenAIClient(provider_config)
    return CustomClient(provider_config)


