from setuptools import setup, find_packages

setup(
    name = "wschat",
    version = "0.6",
    packages = find_packages(exclude=["tests"]),

    author = "Pavel V. Bass",
    author_email = "statgg@gmail.com",
    description = "Simple WebSocket chat"
)
