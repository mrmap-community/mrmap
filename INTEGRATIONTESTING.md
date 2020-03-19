#Integration tests
1. run docker-compose for redis and postgresql

       docker-compose -f docker/docker-compose.yml up

1. run celary

       celary -A MapSkinner worker -l info

1. run integration tests

       python manage.py test --include="integration_tests"