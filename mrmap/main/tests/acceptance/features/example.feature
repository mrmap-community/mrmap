# -- FILE: features/example.feature
Feature: As a User, I want to login so that I can use the MrMap UI.

  Scenario: Successful login process 
    Given User "peter" with "password" is stored at the database 
    Given User "peter" is not logged in
    Given Browser is opened with "localhost"
    When User "peter" enters username and password
    When The user clicks "xpath_to_login_button"
    Then The browser displays the "url_to_dashboard" page
