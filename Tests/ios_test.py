import unittest
import asyncio
from unittest.mock import MagicMock, patch
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.checker_agent import CheckerAgent
from core.context_manager import ContextManager

class TestIOSCheckerAgent(unittest.TestCase):
    """Test the enhanced CheckerAgent with iOS page sources."""

    def setUp(self):
        """Set up the test environment."""
        # Mock context manager
        self.context_manager = ContextManager()
        self.context_manager.set("platform", "ios")
        
        # Mock LLM configuration
        self.llm_config = {
            "model": "test-model",
            "temperature": 0.1
        }
        
        # Create a mock LLM client
        self.mock_llm = MagicMock()
        self.mock_llm.generate_response = MagicMock()
        
        # Mock response object
        mock_response = MagicMock()
        mock_response.content = '{"name": "loginButton"}'
        self.mock_llm.generate_response.return_value = mock_response
        
        # Create the agent with the mock LLM
        with patch('agents.base_agent.BaseAgent._init_llm'):
            self.agent = CheckerAgent("TestCheckerAgent", self.llm_config, self.context_manager)
            self.agent.llm = self.mock_llm
    
    def test_ios_name_matching(self):
        """Test matching iOS elements by name attribute."""
        # iOS page source with name attributes
        page_source = '''
        <AppiumAUT>
          <XCUIElementTypeApplication name="ExampleApp">
            <XCUIElementTypeWindow>
              <XCUIElementTypeOther>
                <XCUIElementTypeTextField name="usernameField" label="Username" value="" />
                <XCUIElementTypeSecureTextField name="passwordField" label="Password" value="" />
                <XCUIElementTypeButton name="loginButton" label="Sign In" />
                <XCUIElementTypeStaticText name="registerLink" label="Create an account" />
              </XCUIElementTypeOther>
            </XCUIElementTypeWindow>
          </XCUIElementTypeApplication>
        </AppiumAUT>
        '''
        
        # Test inputs with slightly different identifiers
        test_cases = [
            ("login", "loginButton"),
            ("username", "usernameField"),
            ("register", "registerLink")
        ]
        
        for input_id, expected_id in test_cases:
            # Override the LLM response for this test case
            mock_response = MagicMock()
            mock_response.content = f'{{"name": "{expected_id}"}}'
            self.mock_llm.generate_response.return_value = mock_response
            
            # Test input
            input_data = {
                "missing_element": input_id,
                "error_message": f"Element not found: {input_id}",
                "page_source": page_source
            }
            
            # Run the agent
            result = asyncio.run(self.agent.execute(input_data))
            
            # Check result
            self.assertIn("name", result, f"Failed to find name for {input_id}")
            self.assertEqual(result["name"], expected_id, 
                            f"Expected {expected_id} but got {result.get('name')}")
    
    def test_ios_label_matching(self):
        """Test matching iOS elements by label attribute."""
        # iOS page source with label attributes
        page_source = '''
        <AppiumAUT>
          <XCUIElementTypeApplication>
            <XCUIElementTypeWindow>
              <XCUIElementTypeOther>
                <XCUIElementTypeStaticText label="Welcome to Example App" />
                <XCUIElementTypeButton label="Continue to App" />
                <XCUIElementTypeButton label="Settings" />
                <XCUIElementTypeStaticText label="Version 1.0.0" />
              </XCUIElementTypeOther>
            </XCUIElementTypeWindow>
          </XCUIElementTypeApplication>
        </AppiumAUT>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"label": "Continue to App"}'
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
        self.assertIn("label", result)
        self.assertEqual(result["label"], "Continue to App")
    
    def test_ios_value_matching(self):
        """Test matching iOS elements by value attribute."""
        # iOS page source with value attributes
        page_source = '''
        <AppiumAUT>
          <XCUIElementTypeApplication>
            <XCUIElementTypeWindow>
              <XCUIElementTypeOther>
                <XCUIElementTypeTextField label="Search" value="iPhone 12" />
                <XCUIElementTypeSlider label="Volume" value="75%" />
                <XCUIElementTypeSwitch label="Enable notifications" value="1" />
              </XCUIElementTypeOther>
            </XCUIElementTypeWindow>
          </XCUIElementTypeApplication>
        </AppiumAUT>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"value": "iPhone 12"}'
        self.mock_llm.generate_response.return_value = mock_response
        
        # Test input
        input_data = {
            "missing_element": "iphone",
            "error_message": "Element not found: iphone",
            "page_source": page_source
        }
        
        # Run the agent
        result = asyncio.run(self.agent.execute(input_data))
        
        # Check result
        self.assertIn("value", result)
        self.assertEqual(result["value"], "iPhone 12")
    
    def test_ios_predicate_generation(self):
        """Test generation of iOS predicates."""
        # iOS page source
        page_source = '''
        <AppiumAUT>
          <XCUIElementTypeApplication>
            <XCUIElementTypeWindow>
              <XCUIElementTypeOther>
                <XCUIElementTypeButton label="Login" name="loginButton" />
                <XCUIElementTypeStaticText label="Forgot password?" />
              </XCUIElementTypeOther>
            </XCUIElementTypeWindow>
          </XCUIElementTypeApplication>
        </AppiumAUT>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"predicate": "label == \\"Login\\""}'
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
        self.assertIn("predicate", result)
        self.assertEqual(result["predicate"], 'label == "Login"')
    
    def test_ios_class_chain_generation(self):
        """Test generation of iOS class chains."""
        # iOS page source
        page_source = '''
        <AppiumAUT>
          <XCUIElementTypeApplication>
            <XCUIElementTypeWindow>
              <XCUIElementTypeOther>
                <XCUIElementTypeScrollView>
                  <XCUIElementTypeOther>
                    <XCUIElementTypeStaticText label="Profile Settings" />
                    <XCUIElementTypeTextField label="Display Name" />
                    <XCUIElementTypeButton label="Save Changes" />
                  </XCUIElementTypeOther>
                </XCUIElementTypeScrollView>
              </XCUIElementTypeOther>
            </XCUIElementTypeWindow>
          </XCUIElementTypeApplication>
        </AppiumAUT>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"class-chain": "**/XCUIElementTypeButton[`label == \\"Save Changes\\"`]"}'
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
        self.assertIn("class-chain", result)
        self.assertEqual(result["class-chain"], '**/XCUIElementTypeButton[`label == "Save Changes"`]')
    
    def test_large_ios_page_source(self):
        """Test with a large iOS page source where the element is beyond 5000 characters."""
        # Create a large iOS page source with the target element at the end
        prefix = '<AppiumAUT><XCUIElementTypeApplication>' + '<XCUIElementTypeOther></XCUIElementTypeOther>' * 500
        target = '<XCUIElementTypeButton name="targetButton" label="Target" />'
        suffix = '</XCUIElementTypeApplication></AppiumAUT>'
        
        page_source = prefix + target + suffix
        
        # Ensure the target element is beyond 5000 characters
        self.assertGreater(len(prefix), 5000)
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"name": "targetButton"}'
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
        self.assertIn("name", result)
        self.assertEqual(result["name"], "targetButton")
    
    def test_ios_complex_hierarchy(self):
        """Test with a complex iOS hierarchy with nested views."""
        # Complex iOS hierarchy with deeply nested elements
        page_source = '''
        <AppiumAUT>
          <XCUIElementTypeApplication name="ExampleApp">
            <XCUIElementTypeWindow>
              <XCUIElementTypeNavigationBar name="ProductDetails">
                <XCUIElementTypeButton name="backButton" label="Back" />
                <XCUIElementTypeStaticText name="titleLabel" label="Product Details" />
              </XCUIElementTypeNavigationBar>
              <XCUIElementTypeScrollView>
                <XCUIElementTypeImage name="productImage" label="Product Image" />
                <XCUIElementTypeStaticText name="productTitle" label="Premium Smartphone" />
                <XCUIElementTypeStaticText name="productPrice" label="$999.99" />
                <XCUIElementTypeStaticText name="descriptionLabel" label="Product Description" />
                <XCUIElementTypeOther>
                  <XCUIElementTypeStaticText name="descriptionText" label="High-resolution display, powerful processor, and advanced camera system." />
                </XCUIElementTypeOther>
                <XCUIElementTypeOther>
                  <XCUIElementTypeButton name="addToCartButton" label="Add to Cart" />
                  <XCUIElementTypeButton name="buyNowButton" label="Buy Now" />
                </XCUIElementTypeOther>
              </XCUIElementTypeScrollView>
            </XCUIElementTypeWindow>
          </XCUIElementTypeApplication>
        </AppiumAUT>
        '''
        
        # Override the LLM response for this test
        mock_response = MagicMock()
        mock_response.content = '{"name": "buyNowButton"}'
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
        self.assertIn("name", result)
        self.assertEqual(result["name"], "buyNowButton")
    
    def test_ios_extractors(self):
        """Test the iOS-specific extractors."""
        # iOS page source
        page_source = '''
        <AppiumAUT>
          <XCUIElementTypeApplication>
            <XCUIElementTypeWindow>
              <XCUIElementTypeOther>
                <XCUIElementTypeButton name="loginButton" label="Login" value="" />
              </XCUIElementTypeOther>
            </XCUIElementTypeWindow>
          </XCUIElementTypeApplication>
        </AppiumAUT>
        '''
        
        # Extract names
        names = self.agent._extract_names(page_source)
        self.assertIn("loginButton", names)
        
        # Extract labels
        labels = self.agent._extract_labels(page_source)
        self.assertIn("Login", labels)
        
        # Extract values (would be empty in this case)
        values = self.agent._extract_values(page_source)
        self.assertEqual(len(values), 0)
        
        # Test iOS predicate generation
        predicates = self.agent._extract_ios_predicates(page_source)
        self.assertTrue(any('name == "loginButton"' in p for p in predicates))
        self.assertTrue(any('label == "Login"' in p for p in predicates))
        
        # Test iOS class chain generation
        class_chains = self.agent._extract_ios_class_chains(page_source)
        expected_chain = '**/XCUIElementTypeButton[`name == "loginButton"`]'
        self.assertTrue(any(expected_chain in c for c in class_chains))

if __name__ == '__main__':
    unittest.main()