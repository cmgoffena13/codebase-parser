from pathlib import Path


def takes_path(p: Path) -> None:
    pass


class RefClass:
    def method(self, p: Path) -> int:
        x: int = 1
        # access reference
        return x + self.value

    def __init__(self):
        self.value = 2


ref = RefClass()
takes_path(Path("."))
