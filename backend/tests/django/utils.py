from datetime import timedelta
from pathlib import Path


class MockResponse:

    def __init__(self, content, status_code=200, elapsed=timedelta(seconds=1), url=""):
        self.status_code = status_code
        self.elapsed = elapsed
        self.url = url

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
