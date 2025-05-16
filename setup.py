from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="bandpics-image-api",
    version="0.1.0",
    author="Jason Ng",
    author_email="jykng@shaw.ca",
    description="The image handler API for bandpics",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jykng-van/bandpics-python-imageapi",
    packages=find_packages(),
    include_package_data=True,
    package_data={"app": ["templates/*"]},
    install_requires=[
        "fastapi>=0.115.12",
        "uvicorn[standard]>=0.34.0",
        "pillow",
        "pymongo",
        "python-multipart",
        "pytest",
        "mongomock",
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-asyncio",
            "httpx",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.12",
    entry_points={
        "console_scripts": [
            "bandpics-image-api=app.main:main",
        ],
    },
)