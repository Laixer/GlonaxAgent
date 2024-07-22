import logging


class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[38;21m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33;1m",
        logging.ERROR: "\033[31;1m",
        logging.CRITICAL: "\033[31;1m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord):
        log_color = self.COLORS.get(record.levelno, self.RESET)
        log_fmt = f"%(asctime)s | {log_color}%(levelname)8s{self.RESET} | %(message)s"
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class ColorLogHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__()
        self.setFormatter(ColorFormatter())
