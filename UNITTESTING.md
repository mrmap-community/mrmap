>all commands are triggered the project root folder.
#Unit tests
1. run docker-compose for redis and postgresql

       docker-compose -f docker/docker-compose.yml up

1. run unit tests

       python manage.py test --include="unit_tests"