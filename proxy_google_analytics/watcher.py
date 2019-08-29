# -*- coding: UTF-8 -*-
from __future__ import absolute_import, unicode_literals

__author__ = 'kuzmenko-pavel'
import socket
from datetime import datetime
from queue import Queue
import pika

from proxy_google_analytics.logger import logger, exception_message
from proxy_google_analytics.worker import Worker

server_name = socket.gethostname()
server_time = datetime.now()


class Watcher(object):
    __slots__ = ['_connection', '_channel', '_closing', '_consumer_tag', '_url', 'queue_name', 'exchange', '_queue',
                 'exchange_type', 'routing_key', 'durable', 'auto_delete', '_messages', '_worker', '_buffer',
                 '_buffer_threshold_length', '_buffer_threshold_time', 'amqp']

    def __init__(self, config, db_click):
        amqp = config.get('amqp', '')
        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._url = amqp.get('broker_url', '')
        self._queue = None
        self.queue_name = amqp.get('queue', 'test')
        self.exchange = amqp.get('exchange', 'test')
        self.exchange_type = amqp.get('exchange_type', 'topic')
        self.routing_key = amqp.get('routing_key', '*')
        self.durable = amqp.get('durable', True)
        self.auto_delete = amqp.get('auto_delete', False)
        self._buffer = set()
        self._buffer_threshold_length = 2
        self._buffer_threshold_time = 2
        self._messages = Queue()
        self._worker = Worker(self._messages, db_click, config)

    def connect(self):
        logger.debug('Connecting to %s', self._url)
        return pika.SelectConnection(pika.URLParameters(self._url),
                                     self.on_connection_open,
                                     stop_ioloop_on_close=False)

    def on_connection_open(self, unused_connection):

        logger.debug('Connection opened')
        self.add_on_connection_close_callback()
        self.open_channel()
        self.timer_buffer_processing()

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
        self.setup_exchange(self.exchange)

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
                                       exchange_type=self.exchange_type, durable=self.durable,
                                       auto_delete=self.auto_delete, passive=False)

    def on_exchange_declareok(self, unused_frame):

        logger.debug('Exchange declared')
        self.setup_queue(self.queue_name)
        self.start_consuming()

    def dummy(self, *args, **kwargs):
        pass

    def setup_queue(self, queue):
        logger.debug('Declaring queue %s', queue)
        self._queue = self._channel.queue_declare(callback=self.dummy, queue=queue, durable=self.durable,
                                                  auto_delete=self.auto_delete)
        logger.debug('Binding %s to %s with %s ', self.exchange, queue, self.routing_key)
        self._channel.queue_bind(callback=self.dummy, queue=queue, exchange=self.exchange, routing_key=self.routing_key)

    def start_consuming(self):

        logger.debug('Issuing consumer related RPC commands')
        self.add_on_cancel_callback()
        self._consumer_tag = self._channel.basic_consume(self.on_message, self.queue_name)

    def add_on_cancel_callback(self):

        logger.debug('Adding consumer cancellation callback')
        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)

    def on_consumer_cancelled(self, method_frame):

        logger.debug('Consumer was cancelled remotely, shutting down: %r',
                     method_frame)
        if self._channel:
            self._channel.close()

    def on_message(self, unused_channel, basic_deliver, properties, body):
        if self.message_processing(unused_channel, basic_deliver, properties, body):
            self.acknowledge_message(basic_deliver.delivery_tag)
        else:
            self.nacknowledge_message(basic_deliver.delivery_tag)

    def message_processing(self, unused_channel, basic_deliver, properties, body):
        try:
            key = basic_deliver.routing_key
            if body:
                msg = body.decode(encoding='UTF-8')
                self._buffer.add((key, msg))
                if len(self._buffer) > self._buffer_threshold_length:
                    self.buffer_processing()
            return True
        except Exception as e:
            logger.error(exception_message(exc=str(e)))
            return False

    def timer_buffer_processing(self):
        logger.debug('Start timer buffer processing')
        self.buffer_processing()
        self._connection.add_timeout(self._buffer_threshold_time, self.timer_buffer_processing)

    def buffer_processing(self):
        logger.debug('Start buffer processing')
        while self._buffer:
            self._messages.put(self._buffer.pop())
        logger.debug('Stop buffer processing')

    def acknowledge_message(self, delivery_tag):
        logger.debug('Acknowledging message %s', delivery_tag)
        self._channel.basic_ack(delivery_tag)

    def nacknowledge_message(self, delivery_tag):
        logger.debug('Acknowledging message %s', delivery_tag)
        self._channel.basic_nack(delivery_tag)

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
        self.buffer_processing()
        self._closing = True
        self._worker.need_exit = True
        self._worker.join()
        self.stop_consuming()
        self._connection.ioloop.start()
        logger.info('Stopped Listening AMQP')

    def close_connection(self):
        logger.debug('Closing connection')
        self._connection.close()
