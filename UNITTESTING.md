>all commands are triggered at the project root folder.

#Unit tests
All unit tests are placed in the tests/unit_tests/ directory. To run only unit tests we can tell the nosetest runner where it has to look for tests.

Run unit tests with following command:

    (venv) $  python manage.py test -s --where="tests/unit_tests/"
