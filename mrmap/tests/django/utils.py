from datetime import timedelta
from pathlib import Path


class MockResponse:

    def __init__(self, status_code, content, elapsed=timedelta(seconds=1)):
        self.status_code = status_code
        self.elapsed = elapsed

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
