import trafaret as t

TRAFARET_CONF = t.Dict({
    t.Key('mongo'): t.Dict({
        t.Key('uri'): t.String(),
    }),
    t.Key('amqp'): t.Dict({
        t.Key('broker_url'): t.String(),
        t.Key('queue'): t.String(),
        t.Key('exchange'): t.String(),
        t.Key('exchange_type'): t.String(),
        t.Key('routing_key'): t.String(),
        t.Key('durable'): t.Bool(),
        t.Key('auto_delete'): t.Bool(),
    }),
})
