>all commands are triggered at the project root folder.

#Integration tests
All integration tests are placed in the tests/integration_tests/ directory. To run only integration tests we can tell the nosetest runner where it has to look for tests.

Before you run integration tests start the celary worker:

    (venv) $ celary -A MapSkinner worker -l info

Run unit tests with following command:

    (venv) $  python manage.py test -s --where="tests/integration_tests/"
