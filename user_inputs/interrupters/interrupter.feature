@InterruptHandler
Feature: Common App Interruptions

  @Handler:PermissionDialog
  Scenario: Handle permission dialog
    Given an interruption occurs
    When I see element "permission_dialog" is displayed
    Then I tap on "allow_button"
    And I wait for 1 second

  @Handler:PromoPopup
  Scenario: Handle promotional popup
    Given an interruption occurs
    When I see element "promo_popup" is displayed
    Then I tap on "close_button"

  @Handler:RateAppDialog
  Scenario: Handle app rating request
    Given an interruption occurs
    When I see element "rate_app_dialog" is displayed
    Then I tap on "maybe_later_button"

  @Handler:LocationPermission
  Scenario: Handle location permission
    Given an interruption occurs
    When I see element "location_permission_dialog" is displayed
    Then I tap on "allow_while_using_app"