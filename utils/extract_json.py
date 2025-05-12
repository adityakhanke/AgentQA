"""
Extract JSON: Utility for extracting JSON content from text responses.

This module provides utilities to extract JSON content from text responses,
handling various formats and edge cases.
"""

import json
import re
from typing import Any, Dict, Optional


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON content from text, handling various formats.

    Args:
        text: Text that may contain JSON
        
    Returns:
        Extracted JSON as dict or None if not found/invalid
    """
    if not text:
        return None
        
    # Try to find JSON in code blocks marked with ```json
    json_code_pattern = r'```json\n(.*?)\n```'
    matches = re.findall(json_code_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            cleaned_match = match.strip()
            return json.loads(cleaned_match)
        except json.JSONDecodeError:
            continue
    
    # Try to find braces that could contain JSON objects
    brace_pattern = r'\{.*\}'
    matches = re.findall(brace_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            # If there are nested objects, this could be complex
            # Only return if we can parse it completely
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue
    
    # Try to find brackets that could contain JSON arrays
    bracket_pattern = r'\[.*\]'
    matches = re.findall(bracket_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue
    
    # Try parsing the entire text as JSON (removing any leading/trailing text)
    cleaned_text = text.strip()
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass
    
    # Final fallback: try to extract JSON-like content with a more liberal approach
    try:
        # Find the first { and last }
        start = text.find('{')
        end = text.rfind('}')
        
        if start != -1 and end != -1 and start < end:
            potential_json = text[start:end+1]
            return json.loads(potential_json)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Could not extract valid JSON
    return None



def extract_json_list(text: str) -> Optional[list]:
    """
    Extract JSON list content from text.
    
    Args:
        text: Text that may contain JSON list
        
    Returns:
        Extracted JSON as list or None if not found/invalid
    """
    if not text:
        return None
        
    # Try to find JSON lists in code blocks
    json_code_pattern = r'```(?:json)?\n(.*?)\n```'
    matches = re.findall(json_code_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            result = json.loads(match.strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            continue
    
    # Try to find brackets that could contain JSON arrays
    bracket_pattern = r'\[.*\]'
    matches = re.findall(bracket_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            result = json.loads(match.strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            continue
    
    # Try parsing the entire text as JSON list
    cleaned_text = text.strip()
    try:
        result = json.loads(cleaned_text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    
    # Final fallback: try to extract JSON-like list content
    try:
        # Find the first [ and last ]
        start = text.find('[')
        end = text.rfind(']')
        
        if start != -1 and end != -1 and start < end:
            potential_json = text[start:end+1]
            result = json.loads(potential_json)
            if isinstance(result, list):
                return result
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Could not extract valid JSON list
    return None

def extract_key_value_pairs(text: str) -> Dict[str, Any]:
    """
    Extract key-value pairs from text that might not be valid JSON.
    
    Args:
        text: Text containing key-value pairs
        
    Returns:
        Dictionary of extracted key-value pairs
    """
    result = {}
    
    # Look for patterns like "key": value or "key" : value
    pattern = r'"([^"]+)"\s*:\s*("[^"]*"|\'[^\']*\'|\d+|\d+\.\d+|true|false|null|\{.*?\}|\[.*?\])'
    matches = re.findall(pattern, text, re.DOTALL)
    
    for key, value in matches:
        try:
            # Try to parse the value as JSON
            parsed_value = json.loads(value)
            result[key] = parsed_value
        except json.JSONDecodeError:
            # If parsing fails, use the string value
            # Strip quotes if present
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                result[key] = value[1:-1]
            else:
                result[key] = value
    
    return result

def format_json(data: Any, indent: int = 2) -> str:
    """
    Format data as a JSON string with proper indentation.
    
    Args:
        data: Data to format as JSON
        indent: Number of spaces for indentation
        
    Returns:
        Formatted JSON string
    """
    return json.dumps(data, indent=indent, ensure_ascii=False)