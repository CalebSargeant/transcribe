from setuptools import setup, find_packages

setup(
    name="transcribe",
    version="2.0.1",
    author="Caleb Sargeant",
    description="Video/audio transcription tool with auto-watch, OpenAI summarization, and Slack notifications",
    py_modules=["transcribe"],
    install_requires=[
        "pyyaml>=6.0",
        "watchdog>=3.0.0",
        "openai>=1.0.0",
        "requests>=2.31.0",
    ],
    entry_points={
        "console_scripts": [
            "transcribe=transcribe:main",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
    ],
)
