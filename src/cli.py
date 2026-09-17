import argparse
from src.config import load_config
from src.logger import setup_logging

logger = setup_logging()
config = load_config()


def crawl() -> None:
    logger.info("Crawl command not yet implemented")


def stats() -> None:
    logger.info("Stats command not yet implemented")


def main() -> None:
    parser = argparse.ArgumentParser(description="Private Search Engine CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("crawl", help="Start crawling")
    subparsers.add_parser("stats", help="Show statistics")

    args = parser.parse_args()

    if args.command == "crawl":
        crawl()
    elif args.command == "stats":
        stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
