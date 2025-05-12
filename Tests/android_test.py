import unittest
import asyncio
from unittest.mock import MagicMock, patch
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.checker_agent import CheckerAgent
from core.context_manager import ContextManager

class TestAndroidCheckerAgent(unittest.TestCase):
    """Test the enhanced CheckerAgent with Android page sources."""

    def setUp(self):
        """Set up the test environment."""
        # Mock context manager
        self.context_manager = ContextManager()
        self.context_manager.set("platform", "android")
        
        # Mock LLM configuration
        self.llm_config = {
            "model": "deepseek-r1-distill-qwen-32b",
            "temperature": 0.1,
            "seed": 42
        }
        
        # Create a mock LLM client
        self.mock_llm = MagicMock()
        self.mock_llm.generate_response = MagicMock()
        
        # Mock response object
        mock_response = MagicMock()
        mock_response.content = '{"resource-id": "com.example.app:id/login_button"}'
        self.mock_llm.generate_response.return_value = mock_response
        
        # Create the agent with the mock LLM
        with patch('agents.base_agent.BaseAgent._init_llm'):
            self.agent = CheckerAgent("TestCheckerAgent", self.llm_config, self.context_manager)
            self.agent.llm = self.mock_llm
    
    def test_android_resource_id_matching(self):
        """Test matching Android resource IDs."""
        # Android page source with resource IDs
        page_source = '''
        <hierarchy>
          <android.widget.FrameLayout resource-id="android:id/content">
            <android.widget.LinearLayout resource-id="com.example.app:id/container">
              <android.widget.EditText resource-id="com.example.app:id/username" hint="Enter username" />
              <android.widget.EditText resource-id="com.example.app:id/password" hint="Enter password" 
                  password="true" />
              <android.widget.Button resource-id="com.example.app:id/login_button" text="Sign In" />
              <android.widget.TextView resource-id="com.example.app:id/register_link" 
                  text="Create an account" clickable="true" />
            </android.widget.LinearLayout>
          </android.widget.FrameLayout>
        </hierarchy>
        '''
        
        # Test inputs with slightly different identifiers
        test_cases = [
            ("login_btn", "com.example.app:id/login_button"),
            ("username_field", "com.example.app:id/username"),
            ("register", "com.example.app:id/register_link")
        ]
        
        for input_id, expected_id in test_cases:
            # Test input
            input_data = {
                "missing_element": input_id,
                "error_message": f"Element not found: {input_id}",
                "page_source": page_source
            }
            
            # Run the agent
            result = asyncio.run(self.agent.execute(input_data))
            
            # Check result
            self.assertIn("resource-id", result, f"Failed to find resource-id for {input_id}")
            self.assertEqual(result["resource-id"], expected_id, 
                            f"Expected {expected_id} but got {result.get('resource-id')}")
    
    def test_android_text_matching(self):
        """Test matching Android elements by text."""
        # Android page source with text attributes
        page_source = '''
        <hierarchy>
          <android.widget.FrameLayout>
            <android.widget.LinearLayout>
              <android.widget.TextView text="Welcome to Example App" />
              <android.widget.Button text="Continue to App" />
              <android.widget.Button text="Settings" />
              <android.widget.TextView text="Version 1.0.0" />
            </android.widget.LinearLayout>
          </android.widget.FrameLayout>
        </hierarchy>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"text": "Continue to App"}'
        self.mock_llm.generate_response.return_value = mock_response
        
        # Test input
        input_data = {
            "missing_element": "continue",
            "error_message": "Element not found: continue",
            "page_source": page_source
        }
        
        # Run the agent
        result = asyncio.run(self.agent.execute(input_data))
        
        # Check result
        self.assertIn("text", result)
        self.assertEqual(result["text"], "Continue to App")
    
    def test_android_content_desc_matching(self):
        """Test matching Android elements by content-desc."""
        # Android page source with content-desc attributes
        page_source = '''
        <hierarchy>
          <android.widget.FrameLayout>
            <android.widget.LinearLayout>
              <android.widget.ImageButton content-desc="Back" />
              <android.widget.TextView text="Product Details" />
              <android.widget.ImageButton content-desc="Add to favorites" />
              <android.widget.ImageButton content-desc="Share product" />
            </android.widget.LinearLayout>
          </android.widget.FrameLayout>
        </hierarchy>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"content-desc": "Add to favorites"}'
        self.mock_llm.generate_response.return_value = mock_response
        
        # Test input
        input_data = {
            "missing_element": "favorite",
            "error_message": "Element not found: favorite",
            "page_source": page_source
        }
        
        # Run the agent
        result = asyncio.run(self.agent.execute(input_data))
        
        # Check result
        self.assertIn("content-desc", result)
        self.assertEqual(result["content-desc"], "Add to favorites")
    
    def test_android_ui_selector_generation(self):
        """Test generation of Android UI selectors."""
        # Android page source
        page_source = '''
        <hierarchy>
          <android.widget.FrameLayout>
            <android.widget.LinearLayout>
              <android.widget.Button text="Login" resource-id="com.example.app:id/login" />
              <android.widget.TextView text="Forgot password?" clickable="true" />
            </android.widget.LinearLayout>
          </android.widget.FrameLayout>
        </hierarchy>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"ui-selector": "new UiSelector().text(\\"Login\\")"}'
        self.mock_llm.generate_response.return_value = mock_response
        
        # Test input
        input_data = {
            "missing_element": "login",
            "error_message": "Element not found: login",
            "page_source": page_source
        }
        
        # Run the agent
        result = asyncio.run(self.agent.execute(input_data))
        
        # Check result
        self.assertIn("ui-selector", result)
        self.assertEqual(result["ui-selector"], 'new UiSelector().text("Login")')
    
    def test_android_xpath_generation(self):
        """Test generation of Android XPath expressions."""
        # Android page source
        page_source = '''
        <hierarchy>
          <android.widget.FrameLayout>
            <android.widget.LinearLayout>
              <android.widget.ScrollView>
                <android.widget.LinearLayout>
                  <android.widget.TextView text="Profile Settings" />
                  <android.widget.EditText hint="Display Name" />
                  <android.widget.Button text="Save Changes" />
                </android.widget.LinearLayout>
              </android.widget.ScrollView>
            </android.widget.LinearLayout>
          </android.widget.FrameLayout>
        </hierarchy>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"xpath": "//android.widget.Button[@text=\'Save Changes\']"}'
        self.mock_llm.generate_response.return_value = mock_response
        
        # Test input
        input_data = {
            "missing_element": "save",
            "error_message": "Element not found: save",
            "page_source": page_source
        }
        
        # Run the agent
        result = asyncio.run(self.agent.execute(input_data))
        
        # Check result
        self.assertIn("xpath", result)
        self.assertEqual(result["xpath"], "//android.widget.Button[@text='Save Changes']")
    
    def test_large_android_page_source(self):
        """Test with a large Android page source where the element is beyond 5000 characters."""
        # Create a large Android page source with the target element at the end
        prefix = '<hierarchy><android.widget.FrameLayout>' + '<android.view.View></android.view.View>' * 500
        target = '<android.widget.Button resource-id="com.example.app:id/target_button" text="Target" />'
        suffix = '</android.widget.FrameLayout></hierarchy>'
        
        page_source = prefix + target + suffix
        
        # Ensure the target element is beyond 5000 characters
        self.assertGreater(len(prefix), 5000)
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"resource-id": "com.example.app:id/target_button"}'
        self.mock_llm.generate_response.return_value = mock_response
        
        # Test input
        input_data = {
            "missing_element": "target",
            "error_message": "Element not found: target",
            "page_source": page_source
        }
        
        # Run the agent
        result = asyncio.run(self.agent.execute(input_data))
        
        # Check result
        # This should find the element even though it's beyond the 5000 character limit
        self.assertIn("resource-id", result)
        self.assertEqual(result["resource-id"], "com.example.app:id/target_button")
    
    def test_android_complex_hierarchy(self):
        """Test with a complex Android hierarchy with nested views."""
        # Complex Android hierarchy with deeply nested elements
        page_source = '''
        <hierarchy>
          <android.widget.FrameLayout>
            <android.widget.LinearLayout>
              <android.widget.Toolbar>
                <android.widget.ImageButton content-desc="Navigate up" />
                <android.widget.TextView text="Product Details" />
              </android.widget.Toolbar>
              <android.widget.ScrollView>
                <android.widget.LinearLayout>
                  <android.widget.ImageView content-desc="Product Image" />
                  <android.widget.TextView text="Premium Smartphone" />
                  <android.widget.TextView text="$999.99" />
                  <android.widget.TextView text="Product Description" />
                  <android.widget.LinearLayout>
                    <android.widget.TextView text="High-resolution display, powerful processor, and advanced camera system." />
                  </android.widget.LinearLayout>
                  <android.widget.LinearLayout>
                    <android.widget.Button text="Add to Cart" resource-id="com.example.app:id/add_to_cart" />
                    <android.widget.Button text="Buy Now" resource-id="com.example.app:id/buy_now" />
                  </android.widget.LinearLayout>
                </android.widget.LinearLayout>
              </android.widget.ScrollView>
            </android.widget.LinearLayout>
          </android.widget.FrameLayout>
        </hierarchy>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"resource-id": "com.example.app:id/buy_now"}'
        self.mock_llm.generate_response.return_value = mock_response
        
        # Test input
        input_data = {
            "missing_element": "buy",
            "error_message": "Element not found: buy",
            "page_source": page_source
        }
        
        # Run the agent
        result = asyncio.run(self.agent.execute(input_data))
        
        # Check result
        self.assertIn("resource-id", result)
        self.assertEqual(result["resource-id"], "com.example.app:id/buy_now")
    
    def test_android_extractors(self):
        """Test the Android-specific extractors."""
        # Android page source
        page_source = '''
        <hierarchy>
          <android.widget.FrameLayout>
            <android.widget.LinearLayout>
              <android.widget.Button text="Login" resource-id="com.example.app:id/login" content-desc="Log in to your account" />
            </android.widget.LinearLayout>
          </android.widget.FrameLayout>
        </hierarchy>
        '''
        
        # Extract resource IDs
        resource_ids = self.agent._extract_resource_ids(page_source)
        self.assertIn("com.example.app:id/login", resource_ids)
        
        # Extract texts
        texts = self.agent._extract_texts(page_source)
        self.assertIn("Login", texts)
        
        # Extract content descriptions
        content_descs = self.agent._extract_content_descs(page_source)
        self.assertIn("Log in to your account", content_descs)
        
        # Test Android UI selector generation
        selectors = self.agent._extract_android_ui_selectors(page_source)
        self.assertTrue(any('new UiSelector().text("Login")' in s for s in selectors))
        self.assertTrue(any('new UiSelector().resourceId("com.example.app:id/login")' in s for s in selectors))

if __name__ == '__main__':
    unittest.main()