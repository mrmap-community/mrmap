from datetime import timedelta
from pathlib import Path


class MockResponse:

    def __init__(self, content, status_code=200, elapsed=timedelta(seconds=1),
                 url="", headers=None):
        self.status_code = status_code
        self.elapsed = elapsed
        self.url = url
        # a real requests.Response always answers its headers; the code under
        # test reads the content type out of them, so the mock carries them
        # too - empty by default, which reads as an unknown content type
        self.headers = headers or {}

        if isinstance(content, Path):
            in_file = open(content, "rb")
            self.content: bytes = in_file.read()
            in_file.close()
            try:
                self.text: str = self.content.decode("UTF-8")
            except UnicodeDecodeError:
                self.text = ""

        if isinstance(content, str):
            self.text: str = content
            self.content: bytes = content.encode("UTF-8")

    @property
    def ok(self):
        return self.status_code < 400 if self.status_code else False
