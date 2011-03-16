# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

from twisted.internet import defer, reactor
from feat.common import log
from feat.agencies.interface import IMessagingPeer
from feat.agents.base.message import BaseMessage


class FinishConnection(Exception):
    pass


class Connection(log.Logger):

    log_category = 'messaging-connection'

    def __init__(self, messaging, agent):
        log.Logger.__init__(self, messaging)
        self._messaging = messaging
        self._agent = IMessagingPeer(agent)

        self._bindings = []
        self._queue_name = self._agent.get_queue_name()
        self._queue = None

    def initiate(self):
        if self._queue_name is not None:
            d = defer.maybeDeferred(self._messaging.defineQueue,
                self._queue_name)
            d.addCallback(self._mainLoop)
        else:
            self.warning('Queue name is None, skipping creating queue '
                         'and consumer.')
            d = defer.succeed(None)
        d.addCallback(lambda _: self)
        return d

    def _mainLoop(self, queue):
        self._queue = queue

        def rebind(_):
            reactor.callLater(0, bind)

        def stop(reason):
            if reason.check(FinishConnection):
                self.log('Error handler: exiting, reason %r' % reason)
            else:
                reason.raiseException()

        def bind():
            d = self._consumeQueue(queue)
            d.addCallbacks(rebind, stop)

        bind()

    def _consumeQueue(self, queue):

        def get_and_call_on_message(message):
            # it is important to always lookup the current message handler
            # maybe someone bound callback to it ?
            on_message = self._agent.on_message
            return on_message(message)

        self._consumeDeferred = queue.get()
        self._consumeDeferred.addCallback(get_and_call_on_message)
        return self._consumeDeferred

    def _append_binding(self, binding):
        self._bindings.append(binding)

    def _remove_binding(self, binding):
        self._bindings.remove(binding)

    # IMessagingClient implementation

    def disconnect(self):
        if self._queue:
            self._queue.stop_consuming()

    def personal_binding(self, key, shard=None):
        if not shard:
            shard = self._agent.get_shard_name()
        return PersonalBinding(self, key=key, shard=shard)

    def publish(self, key, shard, message):
        if not isinstance(message, BaseMessage):
            raise ValueError(
                'Expected third argument to be f.a.b.BaseMessage, '
                'got %r instead' % type(message))
        return self._messaging.publish(key, shard, message)

    def get_bindings(self, shard=None):
        if shard:
            return filter(lambda x: x.shard == shard, self._bindings)
        else:
            return self._bindings

    # end of IMessagingClient implementation


class BaseBinding(object):

    def __init__(self, connection, shard):
        self.connection = connection
        self.connection._append_binding(self)
        self.shard = shard

    def revoke(self):
        self.connection._remove_binding(self)


class PersonalBinding(BaseBinding):

    def __init__(self, connection, shard, key):
        BaseBinding.__init__(self, connection, shard)
        self.key = key
        d = defer.maybeDeferred(
            self.connection._messaging.defineExchange, self.shard)
        d.addCallback(lambda _:
            self.connection._messaging.createBinding(
                 self.shard, self.key, self.connection._queue_name))
        self.created = d

    def revoke(self):
        BaseBinding.revoke(self)
        d = defer.maybeDeferred(
            self.connection._messaging.deleteBinding,
            self.shard, self.key, self.connection._queue_name)
        return d


class Queue(object):

    def __init__(self, name):
        self.name = name
        self._messages = []

        self._consumers = []
        self._send_task = None

    def get(self, *_):
        d = defer.Deferred()
        self._consumers.append(d)
        self._schedule_sending()
        reactor.callLater(0, self._send_messages)
        return d

    def stop_consuming(self):
        ex = FinishConnection("Disconnecting")
        while len(self._consumers) > 0:
            d = self._consumers.pop(0)
            d.errback(ex)
        if self._send_task:
            self._send_task.cancel()

    def enqueue(self, message):
        self._messages.append(message)
        self._schedule_sending()

    def _send_messages(self):
        self._send_task = None
        while len(self._messages) > 0 and len(self._consumers) > 0:
            message = self._messages.pop(0)
            consumer = self._consumers.pop(0)
            consumer.callback(message)

    def _schedule_sending(self):
        if self._send_task is None:
            self._send_task = reactor.callLater(0, self._send_messages)
