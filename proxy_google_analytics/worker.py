import time
from threading import Thread

from proxy_google_analytics.logger import logger, exception_message


class Worker(Thread):
    def __init__(self, queue, db_session, parent_db_session, config):
        super(Worker, self).__init__()
        self.__queue = queue
        self.need_exit = False
        self.session = db_session
        self.parent_session = parent_db_session
        self.config = config
        self.setDaemon(True)
        self.start()

    def run(self):
        logger.info('Starting Worker')
        while not self.need_exit:
            if not self.__queue.empty():
                job = self.__queue.get()
                self.message_processing(*job)
                self.__queue.task_done()
            else:
                time.sleep(1)
        logger.info('Stopping Worker')

    def message_processing(self, key, body):
        try:
            logger.debug('Received message # %s: %s', key, body)
        except Exception as e:
            logger.error(exception_message(exc=str(e)))
