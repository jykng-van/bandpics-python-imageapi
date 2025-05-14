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
    package_data={"fastapi_quickstart": ["templates/*"]},
    install_requires=[
        "fastapi>=0.115.12",
        "uvicorn>=0.34.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.12.3",
    entry_points={
        "console_scripts": [
            "fastapi-quickstart=fastapi_quickstart.main:main",
        ],
    },
)