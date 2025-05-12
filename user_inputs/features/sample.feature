Feature: Task Creation
    As a user
    I want to create a "Task"

    Scenario: create a task
        Given the user is on the "main" screen
        When the user taps on the "add task" button
        And the user enters task name as "YC Conmbinator"
        And the user selects category as "Work"
        And the user selects priority as "High"
        And the user taps on "Add Task" button
        Then the task should be created