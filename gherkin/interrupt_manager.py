from utils.interrupt_handler_parser import InterruptHandlerParser
from core.context_manager import ContextManager
from typing import Any, Dict, Optional, List
from pathlib import Path
from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

class InterruptManager:
    """
    Manages user-defined interrupt handlers in Gherkin format.
    """
    
    def __init__(self, context_manager: ContextManager):
        self.context_manager = context_manager
        self.parser = InterruptHandlerParser()
        self.handlers = {}
        
    def load_handlers_from_directory(self, directory: str) -> None:
        """
        Load all interrupt handlers from a directory.
        
        Args:
            directory: Directory containing handler files
        """
        directory_path = Path(directory)
        if not directory_path.exists() or not directory_path.is_dir():
            logger.warning(f"Interrupt handler directory not found: {directory}")
            return
            
        for file_path in directory_path.glob("**/*.feature"):
            handlers = self.parser.parse_handler_file(str(file_path))
            self.handlers.update(handlers)
            
        logger.info(f"Loaded {len(self.handlers)} interrupt handlers")
        
        # Store handlers in context manager
        self.context_manager.set("interrupt_handlers", self.handlers)
        
    def get_handler(self, handler_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a handler by name.
        
        Args:
            handler_name: Name of the handler
            
        Returns:
            Handler definition or None if not found
        """
        return self.handlers.get(handler_name)
        
    def get_handlers_from_tags(self, tags: List[str]) -> List[Dict[str, Any]]:
        """
        Get handlers referenced by tags.
        
        Args:
            tags: List of tags
            
        Returns:
            List of handler definitions
        """
        handlers = []
        
        for tag in tags:
            if tag.startswith("@CheckInterrupts:"):
                handler_names = tag[16:].split(',')  # Remove "@CheckInterrupts:" prefix
                for name in handler_names:
                    handler = self.get_handler(name.strip())
                    if handler:
                        handlers.append(handler)
                        
        return handlers