import time
from threading import Thread

from proxy_google_analytics.logger import logger, exception_message


class Worker(Thread):
    def __init__(self, queue, db_click, config):
        super(Worker, self).__init__()
        self.__queue = queue
        self.need_exit = False
        self.session = db_click
        self.config = config
        self.setDaemon(True)
        self.start()

    def run(self):
        logger.info('Starting Worker')
        while True:
            if not self.__queue.empty():
                job = self.__queue.get()
                self.message_processing(*job)
                self.__queue.task_done()
            else:
                if self.need_exit:
                    break
                time.sleep(0.1)
        logger.info('Stopping Worker')

    def message_processing(self, key, data):
        try:
            logger.debug('Received message # %s: %s', key, data)
        except Exception as e:
            logger.error(exception_message(exc=str(e)))
