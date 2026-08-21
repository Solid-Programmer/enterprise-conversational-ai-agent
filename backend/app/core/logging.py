import logging


def setup_logging() -> None:
    """Configures application-wide logging format and level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
