from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-renderdoc",
    version="1.0.0",
    description="CLI-Anything harness for RenderDoc — frame-capture graphics debugger",
    long_description=open("RENDERDOC.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="CLI-Anything Contributors",
    license="MIT",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    package_data={
        "cli_anything.renderdoc": ["skills/*.md"],
    },
    python_requires=">=3.8",
    install_requires=[
        "click>=8.0",
        "prompt_toolkit>=3.0",
    ],
    extras_require={
        "dev": ["pytest>=7.0"],
    },
    entry_points={
        "console_scripts": [
            "cli-anything-renderdoc=cli_anything.renderdoc.renderdoc_cli:cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Debuggers",
        "Topic :: Multimedia :: Graphics",
    ],
)
