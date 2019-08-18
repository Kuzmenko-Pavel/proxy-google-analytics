import trafaret as t

TRAFARET_CONF = t.Dict({
    t.Key('mongo'): t.Dict({
        t.Key('uri'): t.String(),
    }),
    t.Key('amqp'): t.String(),
})
