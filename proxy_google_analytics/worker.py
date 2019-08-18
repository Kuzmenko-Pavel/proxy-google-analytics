import time
from threading import Thread
import json

from proxy_google_analytics.google_measurement_protocol import pageview, report
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
            if key == 'action.click':
                self.pageview(json.loads(data))
            else:
                logger.info('Received message # %s: %s', key, data)
        except Exception as e:
            logger.error(exception_message(exc=str(e)))

    def pageview(self, data):
        analytics = self.config.get('analytics', {})
        account_id = data.get('account_id', '')
        referer = data.get('referer')
        url = data.get('url')
        ip = data.get('ip')
        ua = data.get('user_agent')
        cid = data.get('cid')
        analytic = analytics.get(account_id, analytics.get('default'))
        if analytic:
            d = pageview(location=url, referrer=referer, ip=ip, ua=ua)
            r = report(analytic, cid, d)
            print(r)

    def event(self, data):
        pass
