"""
Checker Agent: Enhanced with Screen Definitions and Network Monitoring.

This agent analyzes page source and uses LLM reasoning to find alternative
locators for elements that could not be found with standard approaches.
Now enhanced with screen definition awareness and network monitoring.
"""

import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional

from agents.base_agent import BaseAgent
from core.context_manager import ContextManager
from core.error_handler import handle_error
from tools.tool_registry import get_tools_for_agent
from utils.logger import get_logger
from utils.extract_json import extract_json
from utils.network_monitor import NetworkMonitor

# Configure logger
logger = get_logger(__name__)

class CheckerAgent(BaseAgent):
    """
    Agent responsible for finding UI elements when standard locators fail.
    Enhanced with screen definition awareness and network monitoring.
    """
    
    def __init__(
        self,
        name: str,
        llm_config: Dict[str, Any],
        context_manager: ContextManager
    ):
        """
        Initialize the checker agent.
        
        Args:
            name: Agent name
            llm_config: LLM configuration
            context_manager: Context manager for shared state
        """
        super().__init__(name, llm_config, context_manager)
        self.tools = get_tools_for_agent("checker")
        # Get platform from context manager if available
        self.platform = self.context_manager.get("platform", "android").lower()
        # Track previously suggested corrections to avoid recursion
        self.previous_suggestions = set()
        # Set higher similarity threshold to reduce false matches
        self.similarity_threshold = 0.6
        # Maximum number of windows to send to LLM
        self.max_windows = 3
        # Force LLM usage flag
        self.force_llm_usage = False
        
        # Initialize network monitor
        driver = self.context_manager.get("driver")
        # Get the NetworkMonitor instance
        driver = self.context_manager.get("driver")
        self.network_monitor = NetworkMonitor.get_instance(driver)

        # Store in context if not already there
        if self.network_monitor and not self.context_manager.get("network_monitor"):
            self.context_manager.set("network_monitor", self.network_monitor)
            logger.info(f"Network monitoring initialized in {self.name}")
        
        logger.info(f"Checker agent initialized for platform: {self.platform}")

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Find an alternative locator for a UI element.
        
        Args:
            input_data: Input data containing information about the missing element
                - missing_element: The element that could not be found
                - error_message: Error message from the failed operation
                - page_source: Current page source
                - platform: Optional override for platform (android or ios)
                - retry_count: Number of previous retries (optional)
                - failed_suggestions: List of previously failed suggestions (optional)
                
        Returns:
            Dictionary containing the alternative locator
        """
        try:
            # Extract input data
            missing_element = input_data.get("missing_element")
            error_message = input_data.get("error_message", "")
            page_source = input_data.get("page_source", "")
            platform_override = input_data.get("platform")
            retry_count = input_data.get("retry_count", 0)
            
            # Get failed suggestions from input or previous suggestions set
            failed_suggestions = input_data.get("failed_suggestions", [])
            for failed in failed_suggestions:
                if isinstance(failed, dict):
                    # Add stringified representation
                    self.previous_suggestions.add(str(failed))
                else:
                    self.previous_suggestions.add(str(failed))
            
            # Update platform if override provided
            if platform_override:
                self.platform = platform_override.lower()
                logger.debug(f"Platform override: {self.platform}")
            
            if not missing_element:
                return {"error": "No missing element provided"}
                
            if not page_source:
                return {"error": "No page source provided"}
                
            # Wait for network to become idle before analyzing page
            # This reduces false negatives when content is still loading
            await self.network_monitor.wait_for_network_idle(timeout=2, idle_threshold=0.5)
            
            # Check if this is a retry and if we should force LLM usage
            if retry_count > 0:
                logger.info(f"Retry #{retry_count} - Prioritizing LLM suggestions")
                self.force_llm_usage = True
                
                # Track the failed element
                if str(missing_element) not in self.previous_suggestions:
                    logger.info(f"Adding failed suggestion to history: {missing_element}")
                    self.previous_suggestions.add(str(missing_element))
                else:
                    logger.warning(f"Previously suggested element failed again: {missing_element}")
                
            # If element is an XPath, extract search terms for better matching
            search_terms = self._extract_search_terms(missing_element)
            logger.info(f"Extracted search terms from {missing_element}: {search_terms}")

            # Try the multi-window approach
            llm_suggestion = await self._get_llm_multi_window_suggestion(
                missing_element, error_message, page_source, search_terms
            )
            
            if llm_suggestion:
                validated_suggestion = self._validate_locator(llm_suggestion)
                
                # Check if this suggestion was already tried before
                if str(validated_suggestion) in self.previous_suggestions:
                    logger.warning(f"LLM suggested a previously failed locator: {validated_suggestion}")
                    # Try again explicitly asking for a different suggestion
                    llm_suggestion = await self._get_llm_multi_window_suggestion(
                        missing_element, 
                        error_message, 
                        page_source, 
                        search_terms,
                        avoid_previous=True
                    )
                    if llm_suggestion:
                        validated_suggestion = self._validate_locator(llm_suggestion)
                
                # Track this suggestion for future reference
                self.previous_suggestions.add(str(validated_suggestion))
                logger.info(f"LLM suggested alternative: {validated_suggestion}")
                return validated_suggestion
                
            # If all else fails, try with full page source as a last resort
            if not llm_suggestion:
                logger.warning("No suggestion from multi-window approach, trying with full page source")
                full_page_suggestion = await self._get_llm_suggestion_with_full_page(
                    missing_element, error_message, page_source, list(self.previous_suggestions)
                )
                if full_page_suggestion:
                    validated_suggestion = self._validate_locator(full_page_suggestion)
                    self.previous_suggestions.add(str(validated_suggestion))
                    logger.info(f"Full page LLM suggested alternative: {validated_suggestion}")
                    return validated_suggestion
            
            logger.warning(f"No alternative found for missing element: {missing_element}")
            return {}
            
        except Exception as e:
            error_details = handle_error(e, "Element checking failed")
            logger.error(error_details["message"], exc_info=True)
            
            return {"error": error_details["message"]}
    
    async def _find_from_screen_definitions(
        self, 
        search_key: str, 
        page_source: str,
        search_terms: List[str] = None
    ) -> Optional[Dict[str, str]]:
        """
        Find an element using screen definitions.
        
        Args:
            search_key: The search key to look for
            page_source: Current page source
            search_terms: Optional list of search terms extracted from search key
            
        Returns:
            Dictionary containing the locator or None if not found
        """
        # Get screen registry from context
        screens_registry = self.context_manager.get("screens_registry")
        if not screens_registry:
            return None
        
        # Get current screen context if available
        current_screen = self.context_manager.get("current_screen")
        
        # Try to find the element in screen definitions
        matched_element = None
        highest_score = 0
        
        # If we know the current screen, prioritize its elements
        if current_screen:
            screen_def = screens_registry.get_screen(current_screen)
            if screen_def:
                identifiers = screen_def.get("identifiers", [])
                
                # Check screen identifiers for potential matches
                for element in identifiers:
                    content = element.get("content", "")
                    description = element.get("description", "")
                    
                    if not content and not description:
                        continue
                        
                    # Calculate similarity
                    content_sim = self._calculate_token_similarity(content, search_key)
                    desc_sim = self._calculate_token_similarity(description, search_key)
                    similarity = max(content_sim, desc_sim)
                    
                    if similarity > highest_score and similarity > self.similarity_threshold:
                        highest_score = similarity
                        matched_element = element
        
        # If no match found, try all screens
        if not matched_element:
            for screen_name, screen_def in screens_registry.get_all_screens().items():
                identifiers = screen_def.get("identifiers", [])
                
                for element in identifiers:
                    content = element.get("content", "")
                    description = element.get("description", "")
                    
                    if not content and not description:
                        continue
                        
                    # Calculate similarity
                    content_sim = self._calculate_token_similarity(content, search_key)
                    desc_sim = self._calculate_token_similarity(description, search_key)
                    similarity = max(content_sim, desc_sim)
                    
                    if similarity > highest_score and similarity > self.similarity_threshold:
                        highest_score = similarity
                        matched_element = element
        
        # If we found a matching element, convert it to a locator
        if matched_element:
            return self._convert_element_to_locator(matched_element, page_source)
        
        return None
    
    def _convert_element_to_locator(
        self, 
        element: Dict[str, Any], 
        page_source: str
    ) -> Optional[Dict[str, str]]:
        """
        Convert a screen element definition to a concrete locator.
        
        Args:
            element: Screen element definition
            page_source: Current page source
            
        Returns:
            Dictionary containing the locator or None if not found
        """
        content = element.get("content", "")
        
        if not content:
            return None
            
        # For Android, try text or resource-id
        if self.platform == "android":
            # First try exact text match
            if content in page_source:
                text_pattern = f'text="{content}"'
                if text_pattern in page_source:
                    return {"text": content}
                
                # Then try resource-id
                resource_id_pattern = f'resource-id="[^"]*{content}[^"]*"'
                resource_id_match = re.search(resource_id_pattern, page_source)
                if resource_id_match:
                    resource_id = re.search(r'resource-id="([^"]*)"', resource_id_match.group(0))
                    if resource_id:
                        return {"resource-id": resource_id.group(1)}
                
                # Then try XPath
                return {"xpath": f"//*[contains(@text, '{content}')]"}
        # For iOS, try name, label or XPath
        else:
            # First try name
            name_pattern = f'name="{content}"'
            if name_pattern in page_source:
                return {"name": content}
                
            # Then try label
            label_pattern = f'label="{content}"'
            if label_pattern in page_source:
                return {"label": content}
                
            # Then try XPath
            return {"xpath": f"//*[contains(@name, '{content}') or contains(@label, '{content}')]"}
            
        # Fallback to text
        return {"text": content}
    
    def _extract_search_terms(self, search_key: Any) -> List[str]:
        """
        Extract search terms from a search key.
        
        Args:
            search_key: The search key (could be string, XPath, etc.)
            
        Returns:
            List of search terms
        """
        search_terms = []
        
        # Convert to string if not already
        if not isinstance(search_key, str):
            search_key = str(search_key)
        
        # For XPath expressions, extract terms within quotes
        if search_key.startswith("//"):
            # Extract terms from contains expressions
            contains_terms = re.findall(r"contains\([^,]+,\s*['\"]([^'\"]+)['\"]\)", search_key)
            search_terms.extend(contains_terms)
            
            # Extract terms from direct equality checks 
            equality_terms = re.findall(r"@\w+\s*=\s*['\"]([^'\"]+)['\"]\]", search_key)
            search_terms.extend(equality_terms)
            
            # If no terms found, look for any quoted strings
            if not search_terms:
                quoted_terms = re.findall(r"['\"]([^'\"]+)['\"]", search_key)
                search_terms.extend(quoted_terms)
        else:
            # For regular search keys, tokenize by splitting on non-alphanumeric chars
            tokens = re.findall(r'[a-zA-Z0-9]+', search_key)
            search_terms.extend(tokens)
        
        # Add the original search key as a term if it's not too complex
        if len(search_key) < 30 and not search_key.startswith("//"):
            search_terms.append(search_key)
            
        # If we have a term like "add_task_button", also add split versions
        for term in list(search_terms):  # Create a copy to avoid modification during iteration
            if '_' in term:
                search_terms.extend(term.split('_'))
            elif '-' in term:
                search_terms.extend(term.split('-'))
        
        # Remove duplicates while preserving order
        unique_terms = []
        for term in search_terms:
            if term and term not in unique_terms:
                unique_terms.append(term)
        
        return unique_terms
    
    def _tokenize_identifier(self, identifier: str) -> List[str]:
        """
        Tokenize an identifier into individual words.
        Handles camelCase, snake_case, kebab-case, etc.
        
        Args:
            identifier: The identifier to tokenize
            
        Returns:
            List of tokens
        """
        # Handle camelCase (insert space before uppercase letters preceded by lowercase)
        identifier = re.sub(r'([a-z])([A-Z])', r'\1 \2', identifier)
        
        # Split on common delimiters and non-alphanumeric characters
        tokens = re.split(r'[^a-zA-Z0-9]+', identifier)
        
        # Remove empty tokens and convert to lowercase
        return [token.lower() for token in tokens if token]
    
    def _calculate_token_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate token-based similarity between two strings.
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity score between 0 and 1
        """
        # Convert to strings if they aren't already
        str1 = str(str1) if not isinstance(str1, str) else str1
        str2 = str(str2) if not isinstance(str2, str) else str2
        
        # Tokenize both strings
        tokens1 = set(self._tokenize_identifier(str1))
        tokens2 = set(self._tokenize_identifier(str2))
        
        if not tokens1 or not tokens2:
            return 0.0
            
        # Calculate Jaccard similarity
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        
        if not union:
            return 0.0
            
        return len(intersection) / len(union)
    
    def _extract_element_type_hint(self, search_key: str) -> Optional[str]:
        """
        Extract element type hint from search key.
        
        Args:
            search_key: The search key
            
        Returns:
            Element type hint or None if not found
        """
        # Convert to string if not already
        if not isinstance(search_key, str):
            search_key = str(search_key)
            
        search_key = search_key.lower()
        
        # Common element types to look for
        element_types = {
            "button": ["button", "btn"],
            "input": ["input", "field", "text", "edit"],
            "checkbox": ["checkbox", "check"],
            "switch": ["switch", "toggle"],
            "image": ["image", "img", "icon"],
            "list": ["list", "listview", "recycler"],
            "text": ["text", "label", "textview"],
            "link": ["link"]
        }
        
        # Check if any element type is in the search key
        for element_type, keywords in element_types.items():
            for keyword in keywords:
                if keyword in search_key:
                    return element_type
                    
        return None
    
    async def _get_llm_multi_window_suggestion(
        self, 
        missing_element: str, 
        error_message: str, 
        page_source: str,
        search_terms: List[str],
        avoid_previous: bool = False
    ) -> Optional[Dict[str, str]]:
        """
        Get LLM suggestion using multiple context windows approach.
        
        Args:
            missing_element: The element that could not be found
            error_message: Error message from the failed operation
            page_source: Current page source
            search_terms: Extracted search terms from the missing element
            avoid_previous: Whether to explicitly avoid previous suggestions
            
        Returns:
            Dictionary containing the alternative locator or None if not found
        """
        try:
            # Check if LLM is initialized
            if not self.llm:
                logger.error("LLM not initialized, cannot get suggestions")
                return None
                
            # Extract multiple context windows
            windows = self._extract_multiple_context_windows(page_source, missing_element, search_terms)
            
            if not windows:
                logger.warning("No context windows extracted, using fallback approach")
                # Try the old approach as fallback
                return await self._get_llm_suggestion_fallback(missing_element, error_message, page_source)
                
            # Create a structured prompt for the LLM
            prompt = self._create_multi_window_prompt(
                missing_element, 
                error_message, 
                windows,
                avoid_previous=avoid_previous
            )
            
            # Get LLM response
            llm_response = await self._get_llm_response(prompt)
            
            # Extract JSON from response
            suggestion = extract_json(llm_response)
            if suggestion:
                return suggestion
                
            # If no JSON found, try to extract key-value pairs from the response
            return self._extract_locator_from_text(llm_response)
            
        except Exception as e:
            logger.warning(f"Error in multi-window LLM approach: {str(e)}")
            # Try the old approach as fallback
            return await self._get_llm_suggestion_fallback(missing_element, error_message, page_source)
    
    def _extract_multiple_context_windows(
        self, 
        page_source: str, 
        search_key: str,
        search_terms: List[str],
        max_windows: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Extract multiple context windows from page source.
        
        Args:
            page_source: Page source to extract from
            search_key: The search key
            search_terms: List of search terms
            max_windows: Maximum number of windows to extract
            
        Returns:
            List of context windows
        """
        windows = []
        
        try:
            # Try to parse XML
            try:
                cleaned_source = self._clean_xml(page_source)
                root = ET.fromstring(cleaned_source)
            except Exception as e:
                logger.warning(f"Failed to parse XML: {str(e)}")
                return self._extract_fallback_windows(page_source, search_terms)
                
            # Strategy 1: Find elements by resource-id or name attribute
            id_candidates = self._find_elements_by_attribute_match(
                root, search_terms, ["resource-id", "name", "id"]
            )
            
            # Strategy 2: Find elements by text, content-desc, or label
            text_candidates = self._find_elements_by_attribute_match(
                root, search_terms, ["text", "content-desc", "label", "value"]
            )
            
            # Strategy 3: Find interactive elements like buttons
            element_type = self._extract_element_type_hint(search_key)
            interactive_candidates = self._find_elements_by_type(
                root, element_type, search_terms
            )
            
            # Combine all candidates
            all_candidates = id_candidates + text_candidates + interactive_candidates
            
            # Score candidates by relevance
            scored_candidates = []
            for candidate in all_candidates:
                score = self._score_candidate(candidate, search_key, search_terms)
                scored_candidates.append((candidate, score))
                
            # Sort by score (descending)
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            
            # Get top candidates
            top_candidates = []
            seen_elements = set()
            for candidate, score in scored_candidates:
                # Generate a signature for the element to avoid duplicates
                signature = self._get_element_signature(candidate)
                if signature not in seen_elements and score > 0.3:  # Filter low-quality matches
                    seen_elements.add(signature)
                    top_candidates.append((candidate, score))
                    if len(top_candidates) >= max_windows:
                        break
            
            # Extract well-formed XML for each candidate
            for i, (candidate, score) in enumerate(top_candidates):
                # Get parent, current and children elements
                window_xml = self._get_element_context_xml(candidate)
                
                # Extract match information
                match_info = self._get_element_match_info(candidate, search_terms)
                
                window = {
                    "window_num": i + 1,
                    "match_type": match_info["type"],
                    "match_attribute": match_info["attribute"],
                    "match_value": match_info["value"],
                    "similarity_score": score,
                    "xml": window_xml
                }
                windows.append(window)
                
            # If no windows, try a more aggressive approach
            if not windows:
                return self._extract_fallback_windows(page_source, search_terms)
                
            return windows
                
        except Exception as e:
            logger.warning(f"Error extracting context windows: {str(e)}")
            return self._extract_fallback_windows(page_source, search_terms)
    
    # ... [keeping many of the existing helper methods] ...

    def _clean_xml(self, xml_text: str) -> str:
        """
        Clean XML text by handling common issues.
        
        Args:
            xml_text: XML text to clean
            
        Returns:
            Cleaned XML text
        """
        # Handle <window> wrapper that might have been added
        if xml_text.startswith("<window>"):
            xml_text = xml_text[8:]
        if xml_text.endswith("</window>"):
            xml_text = xml_text[:-9]
            
        # Fix XML declaration if needed
        if not xml_text.startswith("<?xml "):
            xml_text = '<?xml version="1.0" encoding="UTF-8" ?>\n' + xml_text
            
        # Find the first element start and last element end
        first_element_start = xml_text.find("<", xml_text.find("?>"))
        if first_element_start == -1:
            first_element_start = 0
            
        # Try to find a root element name
        root_match = re.search(r'<(\w+)[^>]*>', xml_text[first_element_start:])
        if root_match:
            root_name = root_match.group(1)
            
            # Check if the root element is properly closed
            if f"</{root_name}>" not in xml_text:
                # Wrap everything in the root element
                xml_text = xml_text[:first_element_start] + f"<{root_name}>" + xml_text[first_element_start:] + f"</{root_name}>"
                
        return xml_text
    
    def _extract_fallback_windows(
        self, 
        page_source: str, 
        search_terms: List[str],
        window_size: int = 2000
    ) -> List[Dict[str, Any]]:
        """
        Extract fallback windows when XML parsing fails.
        Uses regex-based approach to find relevant sections.
        
        Args:
            page_source: Page source to extract from
            search_terms: List of search terms
            window_size: Size of the context window
            
        Returns:
            List of context windows
        """
        windows = []
        
        try:
            # Iteratively try each search term
            for i, term in enumerate(search_terms):
                # Skip very short terms
                if len(term) < 3:
                    continue
                    
                # Create patterns to look for
                patterns = []
                
                # For Android
                if self.platform == "android":
                    patterns += [
                        f'resource-id="[^"]*{re.escape(term)}[^"]*"',
                        f'text="[^"]*{re.escape(term)}[^"]*"',
                        f'content-desc="[^"]*{re.escape(term)}[^"]*"',
                        f'class="[^"]*Button[^"]*"[^>]*text="[^"]*"',  # Any button
                        f'clickable="true"'  # Any clickable element
                    ]
                # For iOS
                else:
                    patterns += [
                        f'name="[^"]*{re.escape(term)}[^"]*"',
                        f'label="[^"]*{re.escape(term)}[^"]*"',
                        f'value="[^"]*{re.escape(term)}[^"]*"',
                        f'type="[^"]*Button[^"]*"'  # Any button
                    ]
                
                # Try each pattern
                for pattern in patterns:
                    matches = list(re.finditer(pattern, page_source))
                    
                    # If found matches, extract windows
                    for match_index, match in enumerate(matches[:2]):  # Limit to 2 matches per pattern
                        start_pos = max(0, match.start() - window_size // 2)
                        end_pos = min(len(page_source), match.end() + window_size // 2)
                        
                        # Extract window
                        window_content = page_source[start_pos:end_pos]
                        
                        # Make it well-formed
                        window_xml = self._make_window_well_formed(window_content)
                        
                        # Add window info
                        window = {
                            "window_num": len(windows) + 1,
                            "match_type": f"text-search",
                            "match_attribute": pattern.split('=')[0].replace('"', ''),
                            "match_value": term,
                            "similarity_score": 0.7,  # Default score for regex matches
                            "xml": window_xml
                        }
                        
                        windows.append(window)
                        
                        # Stop if we have enough windows
                        if len(windows) >= self.max_windows:
                            return windows
            
            # If no windows found yet, add the beginning of the page source as fallback
            if not windows and len(page_source) > 0:
                window_xml = self._make_window_well_formed(page_source[:min(len(page_source), window_size)])
                window = {
                    "window_num": 1,
                    "match_type": "fallback",
                    "match_attribute": "none",
                    "match_value": "page_beginning",
                    "similarity_score": 0.3,  # Low score for fallback
                    "xml": window_xml
                }
                windows.append(window)
                
            return windows
            
        except Exception as e:
            logger.warning(f"Error extracting fallback windows: {str(e)}")
            
            # Last resort: just return the whole page source
            if len(page_source) > 0:
                window = {
                    "window_num": 1,
                    "match_type": "full_page",
                    "match_attribute": "none",
                    "match_value": "full_page_source",
                    "similarity_score": 0.1,  # Very low score
                    "xml": f"<window>{page_source}</window>"
                }
                return [window]
            
            return []
    
    def _make_window_well_formed(self, window: str) -> str:
        """
        Try to make a window XML-well-formed by finding complete elements.
        More robust implementation that tries to balance tags.
        
        Args:
            window: Window to make well-formed
            
        Returns:
            Well-formed window
        """
        # Find the first opening tag
        first_open = window.find('<')
        if first_open > 0:
            window = window[first_open:]
            
        # Try to find a complete element by balancing tags
        tag_stack = []
        balanced_end = -1
        
        # Simple tag matching - not perfect but better than before
        for i, char in enumerate(window):
            if char == '<' and i + 1 < len(window):
                # Check if it's a closing tag
                if window[i+1] == '/':
                    tag_close_end = window.find('>', i)
                    if tag_close_end != -1:
                        tag_name = window[i+2:tag_close_end].strip().split()[0]
                        if tag_stack and tag_stack[-1] == tag_name:
                            tag_stack.pop()
                            if not tag_stack:
                                balanced_end = tag_close_end + 1
                                break
                # Check if it's an opening tag
                else:
                    tag_end = window.find('>', i)
                    if tag_end != -1:
                        # Extract tag name
                        tag_content = window[i+1:tag_end]
                        tag_name = tag_content.strip().split()[0]
                        # Skip self-closing tags
                        if not tag_content.endswith('/'):
                            tag_stack.append(tag_name)
        
        # If we found a balanced end, use it
        if balanced_end > 0:
            window = window[:balanced_end]
        else:
            # Fallback: just find the last closing tag
            last_close = window.rfind('>')
            if 0 <= last_close < len(window) - 1:
                window = window[:last_close + 1]
        
        # Wrap in a root element to make it parseable
        return f"<window>{window}</window>"
    
    def _find_elements_by_attribute_match(
        self, 
        root: ET.Element, 
        search_terms: List[str],
        attribute_names: List[str]
    ) -> List[ET.Element]:
        """
        Find elements with attributes matching search terms.
        
        Args:
            root: Root XML element
            search_terms: List of search terms
            attribute_names: List of attribute names to check
            
        Returns:
            List of matching elements
        """
        matches = []
        
        # Iterate through all elements
        for element in root.iter():
            # Check each attribute
            for attr_name in attribute_names:
                attr_value = element.get(attr_name)
                if attr_value:
                    # Check if any search term is in the attribute value
                    for term in search_terms:
                        if term.lower() in attr_value.lower():
                            matches.append(element)
                            break
                    
        return matches
    
    def _find_elements_by_type(
        self, 
        root: ET.Element,
        element_type: Optional[str],
        search_terms: List[str]
    ) -> List[ET.Element]:
        """
        Find elements of a specific type containing search terms.
        
        Args:
            root: Root XML element
            element_type: Type of element to look for (button, input, etc.)
            search_terms: List of search terms
            
        Returns:
            List of matching elements
        """
        matches = []
        
        # Create a map of element types to XML element patterns
        type_patterns = {
            "button": ["Button", "btn"],
            "input": ["EditText", "TextField", "Input"],
            "checkbox": ["CheckBox", "Check"],
            "switch": ["Switch", "Toggle"],
            "image": ["Image", "ImageView", "ImageButton"],
            "list": ["ListView", "RecyclerView", "ScrollView"],
            "text": ["TextView", "Text", "Label"],
            "link": ["Link"]
        }
        
        # Default to button if no type specified
        if not element_type:
            element_type = "button"
            
        # Get patterns for the element type
        patterns = type_patterns.get(element_type, [element_type.capitalize()])
        
        # Find elements matching the patterns
        for element in root.iter():
            # Check if element tag matches any pattern
            element_matches_type = False
            for pattern in patterns:
                if pattern.lower() in element.tag.lower():
                    element_matches_type = True
                    break
                    
            # For Android, also check the 'class' attribute
            if self.platform == "android":
                class_attr = element.get("class", "")
                for pattern in patterns:
                    if pattern.lower() in class_attr.lower():
                        element_matches_type = True
                        break
                        
            # For iOS, check the 'type' attribute
            if self.platform == "ios":
                type_attr = element.get("type", "")
                for pattern in patterns:
                    if pattern.lower() in type_attr.lower():
                        element_matches_type = True
                        break
            
            # Check if the element is clickable (for buttons)
            if element_type == "button" and element.get("clickable") == "true":
                element_matches_type = True
                
            # If element matches type, check if it also matches search terms
            if element_matches_type:
                # Check all attributes for search terms
                for attr_name, attr_value in element.attrib.items():
                    for term in search_terms:
                        if term.lower() in attr_value.lower():
                            matches.append(element)
                            break
                    else:
                        continue
                    break
        
        return matches
    
    def _score_candidate(
        self, 
        element: ET.Element, 
        search_key: str,
        search_terms: List[str]
    ) -> float:
        """
        Score a candidate element based on relevance to search terms.
        
        Args:
            element: Candidate element
            search_key: Original search key
            search_terms: List of search terms
            
        Returns:
            Relevance score (0.0 to 1.0)
        """
        score = 0.0
        
        # Extract element type hint from search key
        element_type_hint = self._extract_element_type_hint(search_key)
        
        # Check if element type matches hint
        element_type_match = 0.0
        if element_type_hint:
            element_tag = element.tag.lower()
            if element_type_hint in element_tag:
                element_type_match = 1.0
            elif element.get("class") and element_type_hint in element.get("class").lower():
                element_type_match = 1.0
                
        # Score key attributes more heavily
        attribute_scores = {}
        key_attributes = []
        
        if self.platform == "android":
            key_attributes = ["resource-id", "text", "content-desc"]
        else:  # iOS
            key_attributes = ["name", "label", "value"]
            
        # Check each attribute for search term matches
        for attr_name, attr_value in element.attrib.items():
            best_term_score = 0.0
            for term in search_terms:
                # Calculate token similarity
                token_sim = self._calculate_token_similarity(term, attr_value)
                
                # Check for exact match
                if term.lower() == attr_value.lower():
                    term_score = 1.0
                # Check for substring match
                elif term.lower() in attr_value.lower():
                    term_score = 0.8
                # Use token similarity
                else:
                    term_score = token_sim * 0.7
                    
                best_term_score = max(best_term_score, term_score)
                
            # Store the best score for this attribute
            attribute_scores[attr_name] = best_term_score
                
        # Calculate weighted score
        for attr_name, attr_score in attribute_scores.items():
            # Prioritize key attributes
            if attr_name in key_attributes:
                score += attr_score * 0.4
            else:
                score += attr_score * 0.1
                
        # Add element type match score
        score += element_type_match * 0.3
        
        # Enhanced clickable element detection
        clickable_score = 0.0
        
        # Android-specific clickable detection
        if self.platform == "android":
            # Direct clickable attribute
            if element.get("clickable") == "true":
                clickable_score = 0.5
                
            # Check for button in element tag
            if "button" in element.tag.lower():
                clickable_score = max(clickable_score, 0.5)
                
            # Check for button classes
            class_attr = element.get("class", "").lower()
            if "button" in class_attr or "btn" in class_attr:
                clickable_score = max(clickable_score, 0.4)
                
            # Check for touchable elements
            if element.get("long-clickable") == "true" or element.get("checkable") == "true":
                clickable_score = max(clickable_score, 0.3)
                
        # iOS-specific clickable detection
        else:
            # Check for button types
            if "button" in element.tag.lower():
                clickable_score = 0.5
                
            # Check for tap gesture recognizers
            if element.get("type", "").lower() in ["xcuielementtypebutton", "xcuielementtypecell"]:
                clickable_score = 0.5
                
            # Check for enabled state
            if element.get("enabled") == "true":
                clickable_score += 0.2
        
        # Higher boost for clickable elements when looking for buttons
        if "button" in search_key.lower() or element_type_hint == "button":
            score += clickable_score
        else:
            score += clickable_score * 0.4
            
        # Normalize score to 0.0-1.0 range
        score = min(1.0, score)
        
        return score
    
    def _get_element_signature(self, element: ET.Element) -> str:
        """
        Get a unique signature for an element to detect duplicates.
        
        Args:
            element: XML element
            
        Returns:
            Element signature string
        """
        # Combine tag and important attributes
        sig_parts = [element.tag]
        
        for attr in ['resource-id', 'id', 'name', 'text', 'content-desc', 'label']:
            if attr in element.attrib:
                sig_parts.append(f"{attr}:{element.get(attr)}")
                
        # Add position information if available
        if 'bounds' in element.attrib:
            sig_parts.append(element.get('bounds'))
            
        return "|".join(sig_parts)
    
    def _get_element_match_info(
        self, 
        element: ET.Element,
        search_terms: List[str]
    ) -> Dict[str, str]:
        """
        Get information about how the element matched the search terms.
        
        Args:
            element: XML element
            search_terms: List of search terms
            
        Returns:
            Dictionary with match information
        """
        match_info = {"type": "unknown", "attribute": "unknown", "value": "unknown"}
        
        # Prioritize key attributes
        key_attributes = []
        if self.platform == "android":
            key_attributes = ["resource-id", "text", "content-desc"]
        else:  # iOS
            key_attributes = ["name", "label", "value"]
            
        # Look for matches in key attributes first
        for attr_name in key_attributes:
            attr_value = element.get(attr_name)
            if attr_value:
                for term in search_terms:
                    if term.lower() in attr_value.lower():
                        match_info["type"] = "attribute_match"
                        match_info["attribute"] = attr_name
                        match_info["value"] = attr_value
                        return match_info
        
        # Check element type
        if "Button" in element.tag or element.get("clickable") == "true":
            match_info["type"] = "element_type"
            match_info["attribute"] = "tag"
            match_info["value"] = element.tag
            return match_info
            
        # Check other attributes
        for attr_name, attr_value in element.attrib.items():
            for term in search_terms:
                if term.lower() in attr_value.lower():
                    match_info["type"] = "attribute_match"
                    match_info["attribute"] = attr_name
                    match_info["value"] = attr_value
                    return match_info
        
        return match_info
    
    def _get_element_context_xml(self, element: ET.Element) -> str:
        """
        Get XML representation of element with its context (parent and siblings).
        
        Args:
            element: XML element
            
        Returns:
            XML string representing the element context
        """
        try:
            # Try to find the parent
            parent = None
            context = None
            
            # Since ElementTree doesn't track parents, we need to rebuild the context
            # Let's create a string representation of this element and important siblings
            
            # First, convert the element itself to string
            element_str = ET.tostring(element, encoding='unicode')
            
            # As a simplification, we'll just use this element with a wrapper
            result = f"<context>\n{element_str}\n</context>"
            
            return result
            
        except Exception as e:
            logger.warning(f"Error getting element context: {str(e)}")
            
            # Fallback: just convert the element to string
            try:
                return ET.tostring(element, encoding='unicode')
            except:
                return f"<element>{str(element.attrib)}</element>"
    
    def _create_multi_window_prompt(
        self, 
        missing_element: str, 
        error_message: str, 
        windows: List[Dict[str, Any]],
        avoid_previous: bool = False
    ) -> str:
        """
        Create a prompt for the LLM using multiple windows.
        
        Args:
            missing_element: The element that could not be found
            error_message: Error message from the failed operation
            windows: List of context windows
            avoid_previous: Whether to explicitly avoid previous suggestions
            
        Returns:
            Prompt for the LLM
        """
        # Create initial prompt with problem description
        prompt = f"""
        You are an expert in mobile UI testing and element identification for {self.platform.upper()} applications.
        
        I'm trying to find an element with identifier: '{missing_element}' but received this error:
        {error_message}
        
        I've extracted {len(windows)} candidate windows from the UI that might contain relevant elements:
        """
        
        # Add each window with its context
        for window in windows:
            prompt += f"""
            
            WINDOW {window['window_num']} (Match: {window['match_type']} - {window['match_attribute']}="{window['match_value']}", Score: {window['similarity_score']:.2f}):
            ```xml
            {window['xml']}
            ```
            """
        
        # Add information about previous failed suggestions if needed
        if avoid_previous and self.previous_suggestions:
            prompt += f"""
            
            IMPORTANT: The following locators have already been tried and failed, DO NOT suggest these again:
            {', '.join(sorted(list(self.previous_suggestions)[:5]))}
            {f"... and {len(self.previous_suggestions) - 5} more" if len(self.previous_suggestions) > 5 else ""}
            
            You MUST suggest a DIFFERENT locator than any of these.
            """
        
        # Add platform-specific instructions
        if self.platform == "android":
            prompt += """
            For Android UI elements, prioritize these locator types in this order:
            1. resource-id: The unique identifier for the element (PREFERRED)
            2. text: The visible text of the element
            3. content-desc: The accessibility description
            4. xpath: XPath expression as a last resort (keep it simple)
            
            Example Android responses:
            {"resource-id": "com.example.app:id/element_id"}
            or
            {"text": "Element Text"}
            or
            {"content-desc": "Element Description"}
            or
            {"xpath": "//android.widget.Button[@text='Element Text']"}
            """
        else:  # iOS
            prompt += """
            For iOS UI elements, prioritize these locator types in this order:
            1. name: The accessibility identifier (PREFERRED)
            2. label: The accessibility label
            3. value: The element's value
            4. xpath: XPath expression as a last resort (keep it simple)
            
            Example iOS responses:
            {"name": "elementName"}
            or
            {"label": "Element Label"}
            or
            {"value": "Element Value"}
            or
            {"xpath": "//XCUIElementTypeButton[@label='Element Label']"}
            """
            
        # Final instructions
        prompt += """
        
        Based on these UI windows, analyze the XML to find the BEST locator for the element that most closely matches '{missing_element}'.
        
        IMPORTANT:
        1. Prioritize resource-id (Android) or name (iOS) locators over XPath whenever possible
        2. If using XPath, keep it simple and avoid complex expressions
        3. Choose the most reliable and unique locator from any window
        4. For buttons or tap targets, look for elements with clickable="true" or Button in the class/tag
        5. Pay special attention to elements where clickable="true" when looking for interactive elements
        
        Return your answer in JSON format with one of the fields based on what you find.
        Return ONLY the JSON without any explanation.
        """

        return prompt
    
    async def _get_llm_response(self, prompt: str) -> str:
        """
        Get response from the LLM.
        
        Args:
            prompt: Prompt for the LLM
            
        Returns:
            LLM response
        """
        try:
            # Check if LLM is initialized
            if not self.llm:
                logger.error("LLM not initialized, cannot get suggestions")
                return ""
                
            # Use the agent's LLM to generate a response
            messages = [
                {"role": "system", "content": f"You are an expert in mobile UI testing and element identification for {self.platform.upper()} applications. Prioritize resource-id over xpath where possible."},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm.generate_response(messages)
            return response.content
            
        except Exception as e:
            logger.warning(f"Error getting LLM response: {str(e)}")
            return ""
    
    async def _get_llm_suggestion_with_full_page(
        self, 
        missing_element: str, 
        error_message: str, 
        page_source: str,
        failed_suggestions: List[str] = []
    ) -> Optional[Dict[str, str]]:
        """
        Method for getting LLM suggestion with the entire page source.
        Used as a last resort when no window-based matches are found.
        
        Args:
            missing_element: The element that could not be found
            error_message: Error message from the failed operation
            page_source: Current page source
            failed_suggestions: List of previously failed suggestions
            
        Returns:
            Dictionary containing the alternative locator or None if not found
        """
        try:
            # Check if LLM is initialized
            if not self.llm:
                logger.error("LLM not initialized, cannot get suggestions")
                return None
                
            # Create a simple prompt with the full page source
            # Truncate page source if it's too large
            max_source_length = 12000  # Increased from 10000
            if len(page_source) > max_source_length:
                truncated_source = page_source[:max_source_length] + "... (truncated)"
            else:
                truncated_source = page_source
                
            prompt = f"""
            You are an expert in mobile UI testing and element identification for {self.platform.upper()} applications.
            
            I'm trying to find an element with identifier: '{missing_element}' but received this error:
            {error_message}
            
            Here is the COMPLETE page source of the app. Make sure to analyze it thoroughly:
            
            ```xml
            {truncated_source}
            ```
            """
            
            # Add information about previous failed suggestions if needed
            if failed_suggestions:
                prompt += f"""
                
                IMPORTANT: The following locators have already been tried and failed, DO NOT suggest these again:
                {', '.join(failed_suggestions[:5])}
                {f"... and {len(failed_suggestions) - 5} more" if len(failed_suggestions) > 5 else ""}
                
                You MUST suggest a DIFFERENT locator than any of these.
                """
            
            # Add platform-specific instructions
            if self.platform == "android":
                prompt += """
                For Android UI elements, look for these attributes in order of preference:
                1. resource-id: The unique identifier (MOST RELIABLE)
                2. text: The visible text 
                3. content-desc: The accessibility description
                4. clickable="true" attribute for interactive elements
                5. class attributes that indicate the element type (Button, TextView, etc.)
                
                Return your answer in JSON format with one of these fields:
                - "resource-id": if you find a matching resource ID
                - "text": if you find matching text content
                - "content-desc": if you find a matching content description
                - "xpath": if you need to provide an XPath expression (as a last resort)
                
                Prioritize resource-id over xpath where possible.
                """
            else:  # iOS
                prompt += """
                For iOS UI elements, look for these attributes in order of preference:
                1. name: The accessibility identifier (MOST RELIABLE)
                2. label: The accessibility label
                3. value: The element's value
                4. type attributes that indicate the element type (Button, etc.)
                
                Return your answer in JSON format with one of these fields:
                - "name": if you find a matching name
                - "label": if you find a matching label
                - "value": if you find a matching value
                - "xpath": if you need to provide an XPath expression (as a last resort)
                
                Prioritize name over xpath where possible.
                """
                
            # Final instructions
            prompt += """
            
            Remember to look for CLICKABLE ELEMENTS when the target appears to be a button.
            Elements with clickable="true" attribute are interactive and often represent buttons.
            
            RETURN ONLY THE JSON without any explanation.
            """
            
            # Get LLM response
            llm_response = await self._get_llm_response(prompt)
            
            # Extract JSON from response
            suggestion = extract_json(llm_response)
            if suggestion:
                return suggestion
            
            # If no JSON found, try to extract locator from text
            return self._extract_locator_from_text(llm_response)
            
        except Exception as e:
            logger.warning(f"Error in full page suggestion: {str(e)}")
            return None
            
    async def _get_llm_suggestion_fallback(
        self, 
        missing_element: str, 
        error_message: str, 
        page_source: str
    ) -> Optional[Dict[str, str]]:
        """
        Fallback method for getting LLM suggestion when multi-window approach fails.
        Used for backward compatibility.
        
        Args:
            missing_element: The element that could not be found
            error_message: Error message from the failed operation
            page_source: Current page source
            
        Returns:
            Dictionary containing the alternative locator or None if not found
        """
        # Just use the full page method as that's more comprehensive
        return await self._get_llm_suggestion_with_full_page(
            missing_element, error_message, page_source, list(self.previous_suggestions)
        )
    
    def _extract_locator_from_text(self, text: str) -> Optional[Dict[str, str]]:
        """
        Extract locator information from text response.
        Platform-aware implementation.

        Args:
            text: Text to extract from
            
        Returns:
            Dictionary containing the locator or None if not found
        """
        # Common locators for both platforms
        common_patterns = [
            (r'text["\']?\s*:\s*["\']([^"\']+)["\']', "text"),
            (r'xpath["\']?\s*:\s*["\']([^"\']+)["\']', "xpath"),
        ]
        
        # Platform-specific patterns
        if self.platform == "android":
            patterns = [
                (r'resource-id["\']?\s*:\s*["\']([^"\']+)["\']', "resource-id"),
                (r'content-desc["\']?\s*:\s*["\']([^"\']+)["\']', "content-desc"),
                (r'ui-selector["\']?\s*:\s*["\']([^"\']+)["\']', "ui-selector"),
            ] + common_patterns
        else:  # iOS
            patterns = [
                (r'name["\']?\s*:\s*["\']([^"\']+)["\']', "name"),
                (r'label["\']?\s*:\s*["\']([^"\']+)["\']', "label"),
                (r'value["\']?\s*:\s*["\']([^"\']+)["\']', "value"),
                (r'predicate["\']?\s*:\s*["\']([^"\']+)["\']', "predicate"),
                (r'class-chain["\']?\s*:\s*["\']([^"\']+)["\']', "class-chain"),
            ] + common_patterns
        
        # Try each pattern, prioritizing resource-id/name over xpath
        result = {}
        for pattern, key in patterns:
            match = re.search(pattern, text)
            if match:
                result[key] = match.group(1)
                # If we found a resource-id or name, return immediately
                if key in ["resource-id", "name"]:
                    return {key: match.group(1)}
        
        # If we found multiple locators, prioritize appropriately
        if result:
            # For Android, prefer resource-id > text > content-desc > xpath
            if self.platform == "android":
                if "resource-id" in result:
                    return {"resource-id": result["resource-id"]}
                elif "text" in result:
                    return {"text": result["text"]}
                elif "content-desc" in result:
                    return {"content-desc": result["content-desc"]}
                elif "xpath" in result:
                    return {"xpath": result["xpath"]}
            # For iOS, prefer name > label > value > xpath
            else:
                if "name" in result:
                    return {"name": result["name"]}
                elif "label" in result:
                    return {"label": result["label"]}
                elif "value" in result:
                    return {"value": result["value"]}
                elif "xpath" in result:
                    return {"xpath": result["xpath"]}
                
        return None
        
    def _validate_locator(self, locator: Dict[str, str]) -> Dict[str, str]:
        """
        Validate a locator to prevent recursion and ensure quality.
        
        Args:
            locator: The locator to validate
            
        Returns:
            Validated locator
        """
        # If locator is empty, return it as is
        if not locator:
            return locator
            
        # Check for XPath recursion
        if "xpath" in locator:
            xpath = locator["xpath"]
            
            # Check if the XPath contains "//" within attribute values
            if "'//" in xpath or "\"//" in xpath:
                logger.warning(f"Detected recursive XPath, simplifying: {xpath}")
                # Try to extract a core search term
                search_terms = re.findall(r"contains\(@\w+,\s*'([^/]+)'\)", xpath)
                if search_terms:
                    term = search_terms[0].split("//")[0].strip()
                    if term:
                        # Create a simpler XPath with the extracted term
                        if self.platform == "android":
                            locator["xpath"] = f"//android.widget.Button[contains(@text, '{term}')]"
                        else:
                            locator["xpath"] = f"//XCUIElementTypeButton[contains(@name, '{term}')]"
                else:
                    # Fallback to extract any content in quotes
                    simple_terms = re.findall(r"'([^']+)'", xpath)
                    if simple_terms:
                        term = simple_terms[0]
                        if self.platform == "android":
                            locator["xpath"] = f"//android.widget.Button[contains(@text, '{term}')]"
                        else:
                            locator["xpath"] = f"//XCUIElementTypeButton[contains(@name, '{term}')]"
                    else:
                        # No viable term found, remove the xpath
                        locator.pop("xpath")
            
            # Check for excessive complexity in XPath
            complexity = xpath.count("contains") + xpath.count("or") + xpath.count("and")
            if complexity > 5:  # Higher threshold for complexity
                logger.warning(f"XPath too complex (score {complexity}), simplifying: {xpath}")
                # Extract element type
                element_type_match = re.match(r'//([^/\[\]]+)', xpath)
                element_type = element_type_match.group(1) if element_type_match else (
                    "android.widget.Button" if self.platform == "android" else "XCUIElementTypeButton"
                )
                
                # Extract the first search term
                search_term_match = re.search(r"contains\(@\w+,\s*'([^']+)'\)", xpath)
                if search_term_match:
                    term = search_term_match.group(1).strip()
                    if term:
                        # Create a simpler XPath with just one condition
                        if self.platform == "android":
                            locator["xpath"] = f"//{element_type}[contains(@text, '{term}')]"
                        else:
                            locator["xpath"] = f"//{element_type}[contains(@name, '{term}')]"
                else:
                    # No viable term found, remove the xpath
                    locator.pop("xpath")
        
        # Prioritize resource-id over xpath if both are present
        if "xpath" in locator and "resource-id" in locator:
            logger.info("Prioritizing resource-id over xpath")
            locator.pop("xpath")
            
        # Ensure text doesn't include XPath expressions
        if "text" in locator and ("//" in locator["text"] or "@" in locator["text"]):
            logger.warning(f"Text contains XPath characters, cleaning: {locator['text']}")
            locator["text"] = re.sub(r'[/\[\]@=]', '', locator["text"])
            
        # Check for empty values
        for key, value in list(locator.items()):
            if not value or len(str(value)) < 1:
                logger.warning(f"Removing empty value for {key}")
                locator.pop(key)
                
        return locator