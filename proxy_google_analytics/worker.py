import time
from threading import Thread
from uuid import uuid4
import json
from prices import Money

from proxy_google_analytics.google_measurement_protocol import pageview, report, event, transaction, item
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
            d = json.loads(data)
            if key == 'action.click':
                self.gpageview(d)
            elif key == 'action.goal':
                self.gevent(d)
            else:
                logger.info('Received message # %s: %s', key, data)
        except Exception as e:
            logger.error(exception_message(exc=str(e)))

    def gpageview(self, data):
        analytics = self.config.get('analytics', {})
        account_id = data.get('account_id', '')
        referer = data.get('referer')
        url = data.get('url')
        ip = data.get('ip')
        ua = data.get('user_agent')
        cid = data.get('cid')
        analytic = analytics.get(account_id, analytics.get('default'))
        if analytic:
            headers = {'User-Agent': ua}
            d = pageview(location=url, referrer=referer, ip=ip, ua=ua)
            report(analytic, cid, d, extra_header=headers)

    def gevent(self, data):
        analytics = self.config.get('analytics', {})
        account_id = data.get('account_id', '')
        referer = data.get('referer')
        currency = data.get('currency')
        url = data.get('url')
        ip = data.get('ip')
        ua = data.get('user_agent')
        price = data.get('price')
        cid = data.get('cid')
        analytic = analytics.get(account_id.lower(), analytics.get('default'))
        if analytic:
            headers = {'User-Agent': ua}
            d = pageview(location=url, referrer=referer, ip=ip, ua=ua)
            e = event('click', 'click', label='click', value=price, uip=ip, dl=url, ua=ua)
            m = Money(price, currency)
            i = item('offer', m, 1)
            t = transaction(transaction_id=str(uuid4()), items=[i], revenue=m, uip=ip, dl=url, ua=ua, pa='purchase')
            report(analytic, cid, d, extra_header=headers)
            report(analytic, cid, e, extra_header=headers)
            report(analytic, cid, t, extra_header=headers)
