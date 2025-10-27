from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kite-websocket",
    version="1.0.0",
    author="Socket Team",
    description="Python client for Zerodha Kite WebSocket API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nawin383/socket",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.7",
    install_requires=[
        "websocket-client>=1.6.0",
        "six>=1.16.0",
        "twisted>=22.10.0",
        "autobahn>=23.1.0",
        "pytz>=2023.3",
    ],
    keywords="kite zerodha websocket trading stocks",
)
