import argparse
import os
import sys
import signal

from trafaret_config import commandline

from proxy_google_analytics.logger import logger, exception_message
from proxy_google_analytics.click_db import get_click_engine
from proxy_google_analytics.utils import TRAFARET_CONF
from proxy_google_analytics.watcher import Watcher


class Daemonize(object):
    __slots__ = ['watcher']

    def __init__(self, config):
        logger.info("Creating daemon.")
        click_engine = get_click_engine(config)
        try:
            self.watcher = Watcher(config, click_engine)
        except Exception as e:
            logger.error(exception_message(exc=str(e)))
            sys.exit(1)

    def start(self):
        logger.info("Add SIGTERM handler")
        signal.signal(signal.SIGTERM, self.sigterm)
        logger.info("Starting daemon.")
        self.action()

    def exit(self):
        self.watcher.stop()
        logger.warn("Stopping daemon.")

    def action(self):
        try:
            self.watcher.run()
        except KeyboardInterrupt:
            self.watcher.stop()

    def sigterm(self, signum, frame):
        self.watcher.stop()


def main(argv):
    dir_path = os.path.dirname(os.path.realpath(__file__))
    ap = argparse.ArgumentParser(description='Great Description To Be Here')
    commandline.standard_argparse_options(ap.add_argument_group('configuration'),
                                          default_config=dir_path + '/../conf.yaml')
    options = ap.parse_args(argv)
    config = commandline.config_from_options(options, TRAFARET_CONF)
    daemon = Daemonize(config=config)
    daemon.start()


if __name__ == '__main__':
    main(sys.argv[1:])
