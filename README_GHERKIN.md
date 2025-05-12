# Guide to Writing Gherkin Tests with Screens and Interrupts

## Introduction

This guide explains how to write effective Gherkin tests for mobile applications using our AI-powered mobile testing framework, with special focus on screen definitions and interrupt handling. These features make your tests more reliable and help them handle real-world scenarios.

## Table of Contents

1. [Setting Up Your Project](#setting-up-your-project)
2. [Defining Screens](#defining-screens)
3. [Handling Interrupts](#handling-interrupts)
4. [Writing Test Features](#writing-test-features)
5. [Running Your Tests](#running-your-tests)
6. [Best Practices](#best-practices)
7. [Complete Examples](#complete-examples)

## Setting Up Your Project

Create the following directory structure for your tests:

```
your_project/
  ├── user_inputs/features/        # Your test features go here
  ├── user_inputs/screens/         # Screen definitions go here
  ├── user_inputs/interrupts/      # Interrupt handlers go here
  └── config/config.yaml      # Configuration file
```

## Defining Screens

Screen definitions tell the framework what key elements identify each screen in your app.

### Step 1: Create a Screen Definition File

For each screen in your app, create a `.feature` file in the `screens/` directory:

```
screens/login_screen.feature
screens/home_screen.feature
screens/profile_screen.feature
```

### Step 2: Write the Screen Definition

Use this template for defining a screen:

```gherkin
@Screen
Feature: Login Screen
  
  @Identity
  Scenario: Screen Identifiers
    Given the screen shows "Log In" button
    And the screen shows "Username" field
    And the screen shows "Password" field
```

Focus on including only the essential, constant elements that uniquely identify this screen. Usually 2-4 key elements are sufficient.

### Step 3: Test Screen Definitions

You can verify your screen definitions using the framework's validation tools:

```bash
python -m framework validate-screens
```

## Handling Interrupts

Interrupts are unexpected dialogs or popups that may appear during test execution, such as permission requests, notifications, or ads.

### Step 1: Create an Interrupt Handler File

Create a `.feature` file in the `interrupts/` directory:

```
interrupts/permission_handlers.feature
interrupts/notification_handlers.feature
```

### Step 2: Write the Interrupt Handler

Use this template for defining interrupt handlers:

```gherkin
@InterruptHandler
Feature: Permission Request Handlers
  
  @Handler:LocationPermission
  Scenario: Handle Location Permission Dialog
    Given I see element "Allow access to your location"
    When I tap on "Allow"
    Then the interrupt is handled
    
  @Handler:CameraPermission
  Scenario: Handle Camera Permission Dialog
    Given I see element "Allow access to your camera"
    When I tap on "Allow"
    Then the interrupt is handled
```

Each handler should:
1. Define a detection condition (`I see element "..."`)
2. Specify the action to take (`I tap on "..."`)

### Step 3: Activate Interrupt Handling in Your Tests

Add tags to your test features or scenarios to enable specific interrupt handlers:

```gherkin
@CheckInterrupts:LocationPermission,CameraPermission
Scenario: Take and share a photo
  ...
```

## Writing Test Features

Now you can write test features that take advantage of screen definitions and interrupt handlers.

### Step 1: Create a Test Feature File

Create a `.feature` file in the `features/` directory:

```
features/login.feature
features/profile_management.feature
```

### Step 2: Write the Test Feature

Use this template for writing a test:

```gherkin
Feature: User Authentication
  As a user
  I want to log in to the application
  So I can access my account

  @CheckInterrupts:NetworkErrorDialog
  Scenario: Successful login with valid credentials
    Given I am on the "Login Screen"
    When I enter "testuser@example.com" in the "Username" field
    And I enter "password123" in the "Password" field
    And I tap the "Log In" button
    Then I should be on the "Home Screen"
    And I should see "Welcome, Test User"
```

Note how the test refers to screens by name and uses the `@CheckInterrupts` tag to specify which interrupts to handle.

### Step 3: Add Step-specific Interrupt Handling

You can also add interrupt handlers to specific steps:

```gherkin
When I tap the "Submit Payment" button @CheckInterrupts:BioAuthPrompt
```

## Running Your Tests

Run your tests using the framework's CLI:

```bash
python main.py --feature features/login.feature --platform android
```

Add screen and interrupt directories if they're not in the default locations:

```bash
python main.py --feature features/login.feature --platform android --screens-dir screens/ --interrupts-dir interrupts/
```

## Best Practices

### For Screen Definitions

1. **Keep it minimal**: Only include elements that are always present and uniquely identify the screen
2. **Avoid dynamic content**: Don't reference elements that change frequently
3. **Prioritize text labels**: Use text that appears on the screen rather than resource IDs
4. **Test on different devices**: Ensure your screen identifiers work across different screen sizes

### For Interrupt Handlers

1. **Be specific**: Make detection conditions specific to avoid false positives
2. **Handle common interrupts**: Create handlers for permissions, network errors, and notifications
3. **Group related handlers**: Place related handlers in the same feature file
4. **Test handlers individually**: Verify each handler works before using it in tests

### For Test Features

1. **Reference screens explicitly**: Always use `I am on the "Screen Name"` and `I should be on the "Screen Name"`
2. **Use descriptive element names**: Describe elements by visible text rather than implementation details
3. **Apply interrupt handlers selectively**: Only enable interrupts relevant to each test
4. **Include verification steps**: Always verify the expected outcome

## Complete Examples

### Screen Definition Example

```gherkin
@Screen
Feature: Profile Screen
  
  @Identity
  Scenario: Screen Identifiers
    Given the screen shows "Profile" in the header
    And the screen shows "Edit Profile" button
    And the screen shows "Settings" option
```

### Interrupt Handler Example

```gherkin
@InterruptHandler
Feature: Common Dialog Handlers
  
  @Handler:RateAppDialog
  Scenario: Handle Rate App Dialog
    Given I see element "Rate your experience"
    When I tap on "Not Now"
    Then the interrupt is handled
  
  @Handler:UpdateAppDialog
  Scenario: Handle App Update Dialog
    Given I see element "Update Available"
    When I tap on "Later"
    Then the interrupt is handled
```

### Test Feature Example

```gherkin
Feature: Profile Management
  
  @CheckInterrupts:RateAppDialog,NetworkErrorDialog
  Scenario: Update user profile information
    Given I am on the "Home Screen"
    When I tap the "Profile" tab
    Then I should be on the "Profile Screen"
    
    When I tap the "Edit Profile" button
    Then I should be on the "Edit Profile Screen"
    
    When I enter "John Smith" in the "Name" field
    And I enter "john.smith@example.com" in the "Email" field
    And I tap the "Save" button @CheckInterrupts:ConfirmationDialog
    Then I should be on the "Profile Screen"
    And I should see "Profile updated successfully"
```

These examples demonstrate how to create comprehensive, robust tests that can handle real-world scenarios in mobile app testing.

---

By following this guide, you can create reliable and maintainable mobile tests that handle interrupts gracefully and correctly validate screens, leading to more stable test automation.