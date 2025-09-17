"""
Setup script for django-bulk-signals.
"""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="django-bulk-signals",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Salesforce-style triggers for Django bulk operations using signals",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/django-bulk-signals",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Framework :: Django",
        "Framework :: Django :: 3.2",
        "Framework :: Django :: 4.0",
        "Framework :: Django :: 4.1",
        "Framework :: Django :: 4.2",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Database",
    ],
    python_requires=">=3.8",
    install_requires=[
        "Django>=3.2",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-django>=4.0",
            "black>=22.0",
            "flake8>=4.0",
            "mypy>=0.900",
        ],
    },
    keywords="django, signals, bulk operations, triggers, salesforce",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/django-bulk-signals/issues",
        "Source": "https://github.com/yourusername/django-bulk-signals",
        "Documentation": "https://github.com/yourusername/django-bulk-signals#readme",
    },
)
