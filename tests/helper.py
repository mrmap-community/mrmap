from django.test import Client
from django.urls import reverse


def _login(username: str, password: str, client: Client):
    client.post(reverse('login', ), data={"username": username, "password": password})
    return client
