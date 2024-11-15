setup(
    name="print-shop-network",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "fastapi==0.104.1",
        "uvicorn==0.24.0",
        "gunicorn==21.2.0",
        "redis==5.0.1",
        "pydantic==2.5.2",
        "requests==2.31.0",
        "python-dotenv==1.0.0"
    ],
    author="Your Name",
    author_email="your.email@example.com",
    description="A distributed print shop network orchestration system",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
)