@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_wfs.json @fixtures:test_csw.json
Feature: Periodic service updates
    A service can have only one unfinished update job.

    Scenario Outline: Reuse unfinished jobs on periodic ticks
        Given the <service> periodic update has a job in state <state>
        When the periodic service update runs twice
        Then the periodic update reuses its unfinished job

        Examples:
            | service | state                  |
            | WFS     | WAITING_FOR_PROCESSING |
            | WFS     | UPDATING               |
            | WFS     | REVIEW_REQUIRED        |
            | CSW     | WAITING_FOR_PROCESSING |
            | CSW     | UPDATING               |
            | CSW     | REVIEW_REQUIRED        |

    Scenario Outline: Create a job after the previous update finished
        Given the <service> periodic update has a job in state UPDATED
        When the periodic service update runs twice
        Then the periodic update creates one new unfinished job

        Examples:
            | service |
            | WFS     |
            | CSW     |
