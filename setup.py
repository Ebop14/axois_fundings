from setuptools import setup, find_packages

setup(
    name="axios-fundings",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "google-auth>=2.0.0",
        "google-auth-oauthlib>=1.0.0",
        "google-api-python-client>=2.0.0",
        "httpx>=0.25.0",
        "dnspython>=2.4.0",
        "pyyaml>=6.0",
        "click>=8.0.0",
    ],
    entry_points={
        "console_scripts": [
            "axios-fundings=src.main:cli",
        ],
    },
    python_requires=">=3.9",
)
