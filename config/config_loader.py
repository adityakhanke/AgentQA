"""
Config Loader: Loads and manages configuration for the testing framework.
"""

import logging
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from utils.logger import get_logger

# Configure logger
logger = get_logger(__name__)

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Dictionary containing configuration
    """
    try:
        config_file = Path(config_path)
        
        if not config_file.exists():
            logger.warning(f"Configuration file not found: {config_path}, using default configuration")
            return get_default_config()
            
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        if not config:
            logger.warning("Empty configuration file, using default configuration")
            return get_default_config()
            
        # Replace environment variables in the configuration
        config = _replace_env_vars(config)
        
        logger.info(f"Loaded configuration from {config_path}")
        return config
        
    except Exception as e:
        logger.error(f"Failed to load configuration from {config_path}: {e}")
        
        # Return default configuration
        logger.info("Using default configuration")
        return get_default_config()

def get_default_config() -> Dict[str, Any]:
    """
    Get default configuration.
    
    Returns:
        Dictionary containing default configuration
    """
    return {
        "appium": {
            "server_url": "http://localhost:4723/wd/hub",
            "implicit_wait_seconds": 10,
            "explicit_wait_seconds": 30,
            "android": {
                "automation_name": "UiAutomator2",
                "device_name": "Android Emulator",
                "platform_version": "",
                "app_package": "",
                "app_activity": "com.shivprakash.to_dolist.MainActivity",
                "no_reset": False,
                "full_reset": False,
                "new_command_timeout": 600
            },
            "ios": {
                "automation_name": "XCUITest",
                "device_name": "iPhone Simulator",
                "platform_version": "",
                "bundle_id": "",
                "no_reset": False,
                "full_reset": False,
                "new_command_timeout": 600,
                "use_new_wda": True,
                "wda_local_port": 8100
            }
        },
        "agents": {
            "parser": {
                "temperature": 0.1,
                "max_tokens": 50000
            },
            "implementor": {
                "temperature": 0.1,
                "max_tokens": 50000
            },
            "executor": {
                "temperature": 0.1,
                "max_tokens": 50000
            },
            "checker": {
                "temperature": 0.1,
                "max_tokens": 50000
            },
            "reporter": {
                "temperature": 0.1,
                "max_tokens": 50000
            }
        },
        "llm": {
            "config_list": [
                {
                    "model": "gpt-4-turbo",
                    "api_key": os.environ.get("OPENAI_API_KEY", ""),
                    "api_base": "https://api.openai.com/v1",
                    "api_type": "openai"
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "top_p": 0.9,
            "request_timeout": 120,
            "retry_count": 3,
            "retry_wait_seconds": 5
        },
        "execution": {
            "screenshot_on_step": True,
            "screenshot_on_error": True,
            "fail_fast": False,
            "default_timeout_ms": 10000,
            "test_parallel": False,
            "test_retry_count": 1
        },
        "reporting": {
            "generate_html": True,
            "include_screenshots": True,
            "include_logs": True,
            "upload_results": False,
            "upload_url": ""
        }
    }

def _replace_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace environment variables in the configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Configuration with environment variables replaced
    """
    if isinstance(config, dict):
        return {k: _replace_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_replace_env_vars(item) for item in config]
    elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
        # Extract environment variable name
        env_var = config[2:-1]
        return os.environ.get(env_var, config)
    else:
        return config

def save_config(config: Dict[str, Any], config_path: str) -> bool:
    """
    Save configuration to a YAML file.
    
    Args:
        config: Configuration to save
        config_path: Path to save the configuration
        
    Returns:
        True if successful, False otherwise
    """
    try:
        config_file = Path(config_path)
        
        # Create parent directories if they don't exist
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Save the configuration
        with open(config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
            
        logger.info(f"Saved configuration to {config_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save configuration to {config_path}: {e}")
        return False