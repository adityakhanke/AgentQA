@Screen
Feature: Login Screen
  
    @Identity
    Scenario: Screen Identifiers
        Given the screen shows "Log in or sign up"
        And has input field for mobile number or email
        And has a continue button