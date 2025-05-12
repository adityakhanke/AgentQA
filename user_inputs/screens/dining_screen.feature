@Screen
Feature: Dining Screen
  
    @Identity
    Scenario: Screen Identifiers
        Given the screen shows "Dining" tab selected

    @ReadyIndicators
    Scenario: Screen Ready State
        Given the section "IN THE LIMELIGHT" has loaded
        And the restaurant listings are visible