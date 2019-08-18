import socket
from datetime import datetime
from queue import Queue
import pika

from proxy_google_analytics.logger import logger, exception_message
from proxy_google_analytics.worker import Worker


server_name = socket.gethostname()
server_time = datetime.now()


class Watcher(object):
    __slots__ = ['_connection', '_channel', '_closing', '_consumer_tag', '_url', '_messages', '_worker']
    EXCHANGE = 'getmyad'
    EXCHANGE_TYPE = 'topic'
    DURABLE = False
    AUTO_DELETE = True
    QUEUES = [x % (server_name, server_time.strftime("%d-%m-%Y_%H:%M:%S:%f")) for x in ['campaign:%s_%s',
                                                                                        'informer:%s_%s',
                                                                                        'account:%s_%s',
                                                                                        'rating:%s_%s',
                                                                                        'domain:%s_%s']]
    ROUTING_KEYS = ['campaign.#', 'informer.#', 'account.#', 'rating.#', 'domain.#']

    def __init__(self, config, db_session, parent_db_session):
        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._url = config['amqp']
        self._messages = Queue()
        self._worker = Worker(self._messages, db_session, parent_db_session, config)

    def connect(self):
        logger.debug('Connecting to %s', self._url)
        return pika.SelectConnection(pika.URLParameters(self._url),
                                     self.on_connection_open,
                                     stop_ioloop_on_close=False)

    def on_connection_open(self, unused_connection):

        logger.debug('Connection opened')
        self.add_on_connection_close_callback()
        self.open_channel()

    def add_on_connection_close_callback(self):

        logger.debug('Adding connection close callback')
        self._connection.add_on_close_callback(self.on_connection_closed)

    def on_connection_closed(self, connection, reply_code, reply_text):

        self._channel = None
        if self._closing:
            self._connection.ioloop.stop()
        else:
            logger.warning('Connection closed, reopening in 5 seconds: (%s) %s',
                           reply_code, reply_text)
            self._connection.add_timeout(5, self.reconnect)

    def reconnect(self):
        self._connection.ioloop.stop()

        if not self._closing:
            # Create a new connection
            self._connection = self.connect()

            # There is now a new connection, needs a new ioloop to run
            self._connection.ioloop.start()

    def open_channel(self):

        logger.debug('Creating a new channel')
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):

        logger.debug('Channel opened')
        self._channel = channel
        self.add_on_channel_close_callback()
        self.setup_exchange(self.EXCHANGE)

    def add_on_channel_close_callback(self):

        logger.debug('Adding channel close callback')
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reply_code, reply_text):

        logger.warning('Channel %i was closed: (%s) %s',
                       channel, reply_code, reply_text)
        self._connection.close()

    def setup_exchange(self, exchange_name):

        logger.debug('Declaring exchange %s', exchange_name)
        self._channel.exchange_declare(callback=self.on_exchange_declareok, exchange=exchange_name,
                                       exchange_type=self.EXCHANGE_TYPE, durable=True, auto_delete=False, passive=False)

    def on_exchange_declareok(self, unused_frame):

        logger.debug('Exchange declared')
        for queue in self.QUEUES:
            self.setup_queue(queue)
        self.start_consuming()

    def dummy(self, *args, **kwargs):
        pass

    def setup_queue(self, queue):
        routing = ''
        logger.debug('Declaring queue %s', queue)
        self._channel.queue_declare(callback=self.dummy, queue=queue, durable=self.DURABLE,
                                    auto_delete=self.AUTO_DELETE, nowait=False)
        for routing_key in self.ROUTING_KEYS:
            queue_name = queue.split(':')[0]
            routing_key_name = routing_key.split('.')[0]
            if queue_name == routing_key_name:
                routing = routing_key
        if len(routing) > 0:
            logger.debug('Binding %s to %s with %s ', self.EXCHANGE, queue, routing)
            self._channel.queue_bind(callback=self.dummy, queue=queue, exchange=self.EXCHANGE, routing_key=routing,
                                     nowait=False)

    def start_consuming(self):

        logger.debug('Issuing consumer related RPC commands')
        self.add_on_cancel_callback()
        for queue in self.QUEUES:
            self._consumer_tag = self._channel.basic_consume(self.on_message, queue)

    def add_on_cancel_callback(self):

        logger.debug('Adding consumer cancellation callback')
        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)

    def on_consumer_cancelled(self, method_frame):

        logger.debug('Consumer was cancelled remotely, shutting down: %r',
                     method_frame)
        if self._channel:
            self._channel.close()

    def on_message(self, unused_channel, basic_deliver, properties, body):
        date = datetime.now().strftime("%d-%m-%Y %H:%M:%S:%f")
        try:
            if basic_deliver.exchange == 'getmyad':
                key = basic_deliver.routing_key
                msg = body.decode(encoding='UTF-8')
                self._messages.put([key, msg])
                logger.debug('%s Saved message # %s from %s - %s: %s %s', date, basic_deliver.delivery_tag,
                             basic_deliver.exchange, basic_deliver.routing_key, properties.app_id, body)
            else:
                logger.debug('Received message # %s from %s - %s: %s %s', basic_deliver.delivery_tag,
                             basic_deliver.exchange, basic_deliver.routing_key, properties.app_id, body)
        except Exception as e:
            logger.error(exception_message(exc=str(e)))
        self.acknowledge_message(basic_deliver.delivery_tag)

    def acknowledge_message(self, delivery_tag):
        logger.debug('Acknowledging message %s', delivery_tag)
        self._channel.basic_ack(delivery_tag)

    def stop_consuming(self):
        if self._channel:
            logger.debug('Sending a Basic.Cancel RPC command to RabbitMQ')
            self._channel.basic_cancel(self.on_cancelok, self._consumer_tag)

    def on_cancelok(self, unused_frame):
        logger.debug('RabbitMQ acknowledged the cancellation of the consumer')
        self.close_channel()

    def close_channel(self):

        logger.debug('Closing the channel')
        self._channel.close()

    def run(self):
        logger.info('Starting Listening AMQP')
        self._connection = self.connect()
        self._connection.ioloop.start()

    def stop(self):
        logger.info('Stopping Listening AMQP')
        self._worker.need_exit = True
        self._closing = True
        self.stop_consuming()
        self._connection.ioloop.start()
        logger.info('Stopped Listening AMQP')

    def close_connection(self):
        logger.debug('Closing connection')
        self._connection.close()
