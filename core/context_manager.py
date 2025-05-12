"""
Context Manager: Provides a thread-safe global context for the mobile testing framework.

This module implements a global context management system that allows 
sharing of configuration and state across different components of the framework.
"""

import threading
from typing import Dict, Any, Optional, Callable, Set

class ContextManager:
    """
    A thread-safe global context manager for sharing state across the framework.
    
    This class provides class-level methods to get, set, and manage 
    a shared context with thread-safe operations.
    """
    
    # Class-level dictionary to store shared context
    _shared_context: Dict[str, Any] = {}
    
    # Thread synchronization lock
    _lock = threading.Lock()
    
    # Listeners for context changes
    _listeners: Dict[str, Set[Callable]] = {}
    _global_listeners: Set[Callable] = set()

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """
        Set a value in the global context.
        
        Args:
            key: The key to store the value under
            value: The value to store
        """
        with cls._lock:
            # Store the old value for comparison
            old_value = cls._shared_context.get(key)
            
            # Update the context
            cls._shared_context[key] = value
            
            # Trigger key-specific listeners
            if key in cls._listeners:
                for listener in cls._listeners[key]:
                    try:
                        listener(key, old_value, value)
                    except Exception as e:
                        print(f"Error in listener for key {key}: {e}")
            
            # Trigger global listeners
            for listener in cls._global_listeners:
                try:
                    listener(key, old_value, value)
                except Exception as e:
                    print(f"Error in global listener: {e}")

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Retrieve a value from the global context.
        
        Args:
            key: The key to retrieve
            default: Default value to return if key not found
        
        Returns:
            The value associated with the key or the default value
        """
        with cls._lock:
            return cls._shared_context.get(key, default)

    @classmethod
    def get_all(cls) -> Dict[str, Any]:
        """
        Get a copy of the entire context.
        
        Returns:
            A dictionary containing all context key-value pairs
        """
        with cls._lock:
            return cls._shared_context.copy()

    @classmethod
    def delete(cls, key: str) -> bool:
        """
        Delete a key from the context.
        
        Args:
            key: The key to delete
        
        Returns:
            True if the key was deleted, False if it didn't exist
        """
        with cls._lock:
            if key in cls._shared_context:
                del cls._shared_context[key]
                return True
            return False

    @classmethod
    def clear(cls) -> None:
        """
        Clear the entire context.
        """
        with cls._lock:
            cls._shared_context.clear()

    @classmethod
    def add_listener(cls, callback: Callable, key: Optional[str] = None) -> None:
        """
        Add a listener for context changes.
        
        Args:
            callback: Function to call when context changes
                     Signature: callback(key, old_value, new_value)
            key: Specific key to listen for changes, or None for all changes
        """
        with cls._lock:
            if key is None:
                # Global listener
                cls._global_listeners.add(callback)
            else:
                # Key-specific listener
                if key not in cls._listeners:
                    cls._listeners[key] = set()
                cls._listeners[key].add(callback)

    @classmethod
    def remove_listener(cls, callback: Callable, key: Optional[str] = None) -> bool:
        """
        Remove a listener for context changes.
        
        Args:
            callback: Function to remove
            key: Specific key the listener was registered for, or None for global
        
        Returns:
            True if the listener was removed, False if not found
        """
        with cls._lock:
            if key is None:
                # Global listener
                if callback in cls._global_listeners:
                    cls._global_listeners.remove(callback)
                    return True
            else:
                # Key-specific listener
                if key in cls._listeners and callback in cls._listeners[key]:
                    cls._listeners[key].remove(callback)
                    if not cls._listeners[key]:
                        del cls._listeners[key]
                    return True
            return False

    @classmethod
    def contains(cls, key: str) -> bool:
        """
        Check if a key exists in the context.
        
        Args:
            key: The key to check
        
        Returns:
            True if the key exists, False otherwise
        """
        with cls._lock:
            return key in cls._shared_context