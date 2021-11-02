Feature: user logout
  As a user
  I want to logout
  so that no unintended or malicious person can use my session with my account

  Background: setup users, log in and open browser
    Given there are set of Users in Database
      | username | password |
      | peter | password123 |
    Given I am logged in
    Given the base url is "https://localhost:8000"
    Given I open the site "/users/dashboard"

  Scenario: User is redirected to login page after logout
    When I click on the element "//*[@id='id_sign_out_btn']"
    Then I expect that the path is "/users/login"

  Scenario: Logged out user tries to open dashboard page. Is redirected to Login page
    When I click on the element "//*[@id='id_sign_out_btn']"
    When I open the site "/users/dashboard"
    Then I expect that the path is "/users/login"

  Scenario: Session ID is cleared after logout
    When I click on the element "//*[@id='id_sign_out_btn']"
    Then I expect that cookie "sessionid" not exists
