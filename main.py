import uvicorn
from src.config import config


def main():
    """Run the application server."""
    uvicorn.run(
        "src.api.app:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
