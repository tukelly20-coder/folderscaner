import sys
import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent, FileMovedEvent


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_logging(log_file):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


class FolderTracker(FileSystemEventHandler):

    def __init__(self, ignore_patterns=None):
        super().__init__()
        self.ignore_patterns = ignore_patterns or []

    def _should_ignore(self, path):
        name = os.path.basename(path)
        for pattern in self.ignore_patterns:
            if name.endswith(pattern.replace("*", "")):
                return True
        return False

    def on_created(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        logging.info("CREATED  %s", event.src_path)

    def on_modified(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        logging.info("MODIFIED %s", event.src_path)

    def on_deleted(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        logging.info("DELETED  %s", event.src_path)

    def on_moved(self, event):
        if event.is_directory or self._should_ignore(event.dest_path):
            return
        logging.info("MOVED    %s -> %s", event.src_path, event.dest_path)


def main():
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "watch_config.json"
    config = load_config(config_path)

    watch_dir = config["watch_dir"]
    log_file = config["log_file"]
    recursive = config.get("recursive", True)
    ignore_patterns = config.get("ignore_patterns", [])

    if not os.path.isdir(watch_dir):
        print(f"Watch directory does not exist: {watch_dir}", file=sys.stderr)
        sys.exit(1)

    setup_logging(log_file)
    logging.info("=" * 60)
    logging.info("Starting folder tracker")
    logging.info("Watch dir : %s", watch_dir)
    logging.info("Log file  : %s", log_file)
    logging.info("Recursive : %s", recursive)
    logging.info("Ignore    : %s", ignore_patterns)
    logging.info("Started at: %s", datetime.now().isoformat())
    logging.info("=" * 60)

    event_handler = FolderTracker(ignore_patterns=ignore_patterns)
    observer = Observer()
    observer.schedule(event_handler, path=watch_dir, recursive=recursive)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping observer...")
        observer.stop()
    observer.join()
    logging.info("Observer stopped.")


if __name__ == "__main__":
    main()
