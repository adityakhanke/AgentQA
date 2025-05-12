# AgnetQA - Enhanced Mobile Testing Framework

An AI-powered, production-ready mobile testing framework that combines the best of both worlds. This framework leverages LLMs to understand Gherkin specifications, convert them to executable test steps, and intelligently interact with mobile applications through Appium.

## Key Features

- **Gherkin-Driven Testing**: Write tests in natural language using Gherkin syntax
- **AI-Powered Interpretation**: LLMs parse and map test steps to executable commands
- **Enhanced Element Finding**: Multi-strategy element finding with AI-assisted correction
- **Robust Error Recovery**: Automatic retry and element correction mechanisms
- **Cross-Platform Support**: Works with both Android and iOS applications
- **Comprehensive Reporting**: Detailed test reports with screenshots and metrics

## Architecture

The framework uses a multi-agent architecture where specialized AI agents work together:

1. **Parser Agent**: Analyzes Gherkin specs and extracts structured test steps
2. **Implementor Agent**: Maps test steps to executable tool commands
3. **Executor Agent**: Executes the test steps using registered tools
4. **Checker Agent**: Helps find UI elements when standard locators fail
5. **Reporter Agent**: Generates comprehensive test reports

These agents are orchestrated by the Test Orchestrator and communicate through a shared Context Manager.

## Prerequisites

- Python 3.8+
- Appium Server 2.0+
- Android SDK (for Android testing)
- Xcode (for iOS testing)
- An OpenAI API key or other LLM provider

## Installation

1. Clone the repository:
```bash
git clone https://github.com/adityakhanke/AgentQA.git
cd agentqa
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
export OPENAI_API_KEY=your_openai_api_key
```

4. Start the Appium server:
```bash
appium
```

## Configuration

The framework uses YAML configuration files to configure all aspects of the testing process. The default configuration file is located at `config/default_config.yaml`.

### Appium Configuration

```yaml
appium:
  server_url: "http://localhost:4723/wd/hub"
  
  # Android Configuration
  android:
    automation_name: "UiAutomator2"
    device_name: "Android Emulator"
    app_package: "com.example.app"
    app_activity: "com.example.app.MainActivity"
    
  # iOS Configuration
  ios:
    automation_name: "XCUITest"
    device_name: "iPhone Simulator"
    bundle_id: "com.example.app"
```

### LLM Configuration

```yaml
llm:
  config_list:
    - model: "gpt-4-turbo"
      api_key: "${OPENAI_API_KEY}"  # Uses environment variable
      api_base: "https://api.openai.com/v1"
      api_type: "openai"
  temperature: 0.1
  max_tokens: 2000
```

## Writing Test Cases

Test cases are written in Gherkin format, a business-readable domain-specific language for behavior descriptions.

Example:

```gherkin
Feature: Login Functionality
  As a user
  I want to log in to the application
  So that I can access my account

  Scenario: Successful login with valid credentials
    Given the app is launched
    When I enter "testuser@example.com" in the email field
    And I enter "Password123" in the password field
    And I tap the "Login" button
    Then I should see the "Dashboard" screen
    And I should see the text "Welcome, Test User"
```

Save this file as `features/login.feature`.

## Running Tests

Run tests using the command line interface:

```bash
# Run all feature files in a directory
python main.py --feature features/ --platform android

# Run a specific feature file
python main.py --feature features/login.feature --platform ios --app path/to/your/app.ipa

# Run with verbose logging and screenshots
python main.py --feature features/ --platform android --verbose --screenshots
```

### Command Line Options

- `--feature`, `-f`: Path to Gherkin feature file or directory
- `--platform`, `-p`: Target platform (android or ios)
- `--app`, `-a`: Path to app package/bundle
- `--verbose`, `-v`: Enable verbose logging
- `--report-dir`, `-r`: Directory to store test reports
- `--screenshots`, `-s`: Take screenshots during test execution
- `--fail-fast`, `-ff`: Stop test execution on first failure
- `--timeout`, `-t`: Default timeout in seconds
- `--retries`: Number of retries for failed steps

## Understanding the Tool Registry

The framework uses a tool registry pattern to make mobile interactions available to the AI agents. This design allows for easy extension and discoverability of tools.

Example tool registration:

```python
@tool(
    agent_names=["executor", "checker"],
    description="Single tap on an element",
    name="single_tap",
    parameters={
        "search_key": {
            "type": "string",
            "description": "Element identifier (ID, text, etc.)"
        }
    }
)
async def single_tap(search_key: str) -> Dict[str, Any]:
    """Implementation of the single tap function"""
    ...
```

## Enhanced Element Finding

One of the framework's key strengths is its multi-strategy approach to finding UI elements. When a standard locator fails, the framework:

1. Tries alternative locator strategies (ID, accessibility ID, text, class, etc.)
2. Uses platform-specific approaches (UiAutomator for Android, Predicates for iOS)
3. Applies AI-assisted correction via the Checker Agent
4. Retries the operation if a better locator is found

This makes the tests much more robust against UI changes and locator fragility.

## Test Execution Flow

1. **Parsing**: The Parser Agent converts Gherkin into structured test steps
2. **Mapping**: The Implementor Agent maps steps to executable commands
3. **Execution**: The Executor Agent executes the commands using tools
4. **Validation**: The Checker Agent helps find elements when standard approaches fail
5. **Reporting**: The Reporter Agent generates comprehensive test reports

## Adding Custom Tools

To add custom mobile interactions, create a new module in the `tools` directory and register your functions using the `@tool` decorator:

```python
from tools.tool_registry import tool

@tool(
    agent_names=["executor"],
    description="Your custom tool description",
    name="custom_tool",
    parameters={
        "param1": {
            "type": "string",
            "description": "Parameter description"
        }
    }
)
async def custom_tool(param1: str) -> Dict[str, Any]:
    """
    Your custom tool implementation.
    """
    # Implementation
    ...
    
    return {"message": "Success", "details": "Operation completed"}
```

## Viewing Reports

After test execution, reports are generated in the specified report directory (default: `test_reports`). The reports include:

- Test execution details and results
- Screenshots of the application state
- Timing and performance metrics
- Error details and retry information

## Error Handling and Recovery

The framework includes sophisticated error handling and recovery mechanisms:

1. **Step Retries**: Failed steps are retried with increasing timeouts
2. **Element Correction**: The Checker Agent suggests alternative locators
3. **Context Preservation**: Test state is maintained across retries
4. **Detailed Logging**: Comprehensive logging helps diagnose issues

## Best Practices

1. **Write Clear Gherkin**: Use simple, clear language in your feature files
2. **Use Unique Identifiers**: Add accessibility labels to your app for easier testing
3. **Organize Features**: Create separate feature files for different functional areas
4. **Set Appropriate Timeouts**: Adjust timeouts based on app and device performance
5. **Review Reports**: Regularly review test reports to identify fragile tests

## Contributing

Contributions to the framework are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch
3. Add your feature or fix
4. Write tests for your changes
5. Submit a pull request

