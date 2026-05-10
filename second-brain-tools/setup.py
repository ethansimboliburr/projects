from setuptools import setup, find_packages

setup(
    name="second-brain-tools",
    version="1.0.0",
    packages=find_packages(),
    py_modules=[
        "main", "vault_cli", "coop_bot", "academic_assistant",
        "calendar_sync", "brain", "inbox_watcher", "screenshot_parser",
        "config", "templates", "utils",
    ],
    install_requires=[
        "anthropic",
        "click",
        "python-dotenv",
        "google-api-python-client",
        "google-auth-httplib2",
        "google-auth-oauthlib",
        "watchdog",
        "requests",
        "beautifulsoup4",
        "pyyaml",
        "rich",
        "flask",
        "pillow",
    ],
    entry_points={
        "console_scripts": [
            "vault=vault_cli:cli",
        ],
    },
    python_requires=">=3.10",
)
