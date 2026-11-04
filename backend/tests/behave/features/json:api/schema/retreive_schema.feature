@no_fixtures
Feature: OpenApi Schema
    As an API client,
    I want to fetch the openapi schema,
    so that I can configure the client dynamic based on the schema.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/schema
        # the openapi schema view renders the schema document, not json:api
        Given I set the header "HTTP_ACCEPT" with value "application/json"

    Scenario: Can retreive as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200

    Scenario: Can retreive as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200

    Scenario: Can retreive in german
        Given I set the cookie "django_language" with value "de"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "components.schemas.WebMapService.properties.attributes.properties.title.title" with value "Titel"
        Then I expect that response json has an attribute "components.schemas.WebMapService.properties.attributes.properties.isSearchable.title" with value "Durchsuchbar"
        Then I expect that response json has an attribute "components.schemas.WebMapService.properties.attributes.properties.isSearchable.description" with value "Nur Metadatensätze welche gesucht werden dürfen, werden von der Suchschnittstelle zurückgeliefert."
        Then I expect that response json has an attribute "components.schemas.WebMapService.properties.attributes.properties.abstract.title" with value "Beschreibung"
        Then I expect that response json has an attribute "components.schemas.WebMapService.properties.attributes.properties.abstract.description" with value "Kurzfassung des Inhalts"

    Scenario: Paginated list operations document their sort enum
        # issue #944: every paginated list endpoint polices `sort` with a 400,
        # so each one has to document the parameter with its valid terms -
        # one per shape: implicit serializer fields, nested related list,
        # tuple whitelist and hand-written sort (plus the choice lists of #943)
        When I send the request with GET method
        Then I expect the openapi schema operation "get" on "/api/registry/keywords" documents a sort enum
        Then I expect the openapi schema operation "get" on "/api/accounts/groups" documents a sort enum
        Then I expect the openapi schema operation "get" on "/api/accounts/users/{UserId}/groups" documents a sort enum
        Then I expect the openapi schema operation "get" on "/api/registry/layers/{LayerId}/keywords" documents a sort enum
        Then I expect the openapi schema operation "get" on "/api/registry/update/webmapservice-update-jobs" documents a sort enum
        Then I expect the openapi schema operation "get" on "/api/registry/service-alerts" documents a sort enum
        Then I expect the openapi schema operation "get" on "/api/registry/languages" documents a sort enum
