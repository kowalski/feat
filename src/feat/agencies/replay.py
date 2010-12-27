from zope.interface import implements

from feat.common import serialization, log
from feat.agents.base import replay
from feat.common.serialization import pytree
from feat.interface import agent, journal
from feat.interface.serialization import (IRestorator, ISerializable,
                                          IExternalizer, )


class Replay(log.FluLogKeeper, log.Logger):
    '''
    Class managing the replay of the single agent.
    '''

    implements(IExternalizer)

    log_category = 'replay-driver'

    def __init__(self, journal, agent_id):
        log.FluLogKeeper.__init__(self)
        log.Logger.__init__(self, self)

        self.journal = journal
        self.unserializer = pytree.Unserializer(externalizer=self)
        self.serializer = pytree.Serializer(externalizer=self)

        self.agent_id = agent_id
        Factory(self, 'agent-medium', AgencyAgent)
        Factory(self, 'replier-medium', AgencyReplier)
        Factory(self, 'requester-medium', AgencyRequester)
        Factory(self, 'contractor-medium', AgencyContractor)
        Factory(self, 'manager-medium', AgencyManager)
        Factory(self, 'agency-interest', Interest)

        self.reset()

    def reset(self):
        # registry of Recorders: journal_id -> IRecorderNode
        self.registry = dict()
        self.medium = None
        self.agent = None
        # registry of dummy medium classes: id(instance) -> medium
        self.dummies = dict()

    def register(self, recorder):
        j_id = recorder.journal_id
        self.log('Registering recorder: %r, id: %r',
                 recorder.__class__.__name__, j_id)
        assert j_id not in self.registry
        self.registry[j_id] = recorder

    def set_aa(self, medium):
        assert self.medium is None
        self.medium = medium

    def __iter__(self):
        return self

    def next(self):
        entry = self.journal.next()
        (agent_id, instance_id, entry_id, fiber_id, fiber_depth,
        input, side_effects, output, ) = entry
        input = self.unserializer.convert(input)
        side_effects = self.unserializer.convert(side_effects)

        assert agent_id == self.agent_id
        if instance_id == 'agency':
            self.log("<----------------- Applying entry:\n  Entry_id: %r.\n  "
                     "Input: %r", entry_id, input)
            method = getattr(self, "entry_%s" % entry_id)
            replay.replay(method, input)
            return self.next()
        else:
            instance = self.registry.get(instance_id, None)
            if instance is None:
                raise ValueError("Instance_id %r not found in the registry. "
                                 "Tried to call entry_id: %r" %\
                                 (str(instance_id), entry_id, ))
            self.log("<----------------- Applying entry:\n  Entry_id: %r.\n  "
                     "Input: %r.\n  Side effects: %r.\n  Output: %r.",
                     entry_id, input, side_effects, output)
            r_se, result = instance.replay(entry_id, input, side_effects)
            result = self.serializer.freeze(result)
            self.log("State after the entry: %r", self.agent._get_state())
            return r_se, result, output

    def entry_agent_created(self, agent_factory, dummy_id):
        assert self.medium is None
        self.medium = AgencyAgent(self)
        self.register_dummy(dummy_id, self.medium)
        self.agent = agent_factory(self.medium)

    def entry_agent_deleted(self):
        raise NotImplemented('TODO')

    def entry_protocol_created(self, protocol_factory, medium, args, kwargs):
        assert self.agent is not None
        args = args or tuple()
        kwargs = kwargs or dict()
        protocol_factory(self.agent, medium, *args, **kwargs)

    def entry_protocol_deleted(self, journal_id, dummy_id):
        del(self.registry[journal_id])
        self.unregister_dummy(dummy_id)

    def entry_snapshot(self, snapshot):
        self.reset()
        self.agent, self.protocols = self.unserializer.convert(snapshot)

    # Managing the dummy registry:

    def register_dummy(self, dummy_id, dummy):
        if self.lookup_dummy(dummy_id) is not None:
            raise RuntimeError("Tried to register dummy: %r class: %r second"
                               " time", dummy_id, dummy.__class__.__name__)
        self.dummies[dummy_id] = dummy

    def unregister_dummy(self, dummy_id):
        if self.lookup_dummy(dummy_id) is None:
            raise RuntimeError("Treid to unregister dummy_id: %r "
                               "but not found.", dummy_id)
        del(self.dummies[dummy_id])

    def lookup_dummy(self, dummy_id):
        return self.dummies.get(dummy_id, None)

    # IExternalizer

    def identify(self, _):
        raise RuntimeError("OOPS, this should not be used in replay")

    def lookup(self, identifier):
        return self.registry.get(identifier, None)


class BaseReplayDummy(object):

    def restored(self):
        pass


class StateMachineSpecific(object):

    @serialization.freeze_tag('StateMachineMixin.wait_for_state')
    def wait_for_state(self, state):
        raise RuntimeError('This should never be called!')


class Factory(serialization.Serializable):

    implements(IRestorator)

    def __init__(self, replay, type_name, cls):
        self.replay = replay
        self.type_name = type_name
        self.cls = cls
        serialization.register(self)

    def restore(self, dummy_id):
        existing = self.replay.lookup_dummy(dummy_id)
        if existing:
            return existing
        new = self.cls(self.replay)
        self.replay.register_dummy(dummy_id, new)
        return new

    def prepare(self):
        return None


class AgencyAgent(log.LogProxy, log.Logger, BaseReplayDummy):

    implements(agent.IAgencyAgent, journal.IRecorderNode,
               journal.IJournalKeeper, ISerializable)

    def __init__(self, replay):
        log.LogProxy.__init__(self, replay)
        log.Logger.__init__(self, replay)
        self.journal_keeper = replay
        self.replay = replay
        self.replay.set_aa(self)

    def restored(self):
        pass

    @replay.named_side_effect('AgencyAgent.get_descriptor')
    def get_descriptor(self):
        pass

    @replay.named_side_effect('AgencyAgent.get_time')
    def get_time(self):
        pass

    @replay.named_side_effect('AgencyAgent.join_shard')
    def join_shard(self, shard):
        pass

    @replay.named_side_effect('AgencyAgent.initiate_protocol')
    def initiate_protocol(self, factory, recipients, *args, **kwargs):
        pass

    @replay.named_side_effect('AgencyAgent.revoke_interest')
    def revoke_interest(self, factory):
        pass

    @replay.named_side_effect('AgencyAgent.register_interest')
    def register_interest(self, factory):
        pass

    @serialization.freeze_tag('AgencyAgency.save_document')
    def save_document(self, document):
        raise RuntimeError('This should never be called!')

    @serialization.freeze_tag('AgencyAgency.reload_document')
    def reload_document(self, document):
        raise RuntimeError('This should never be called!')

    @serialization.freeze_tag('AgencyAgency.delete_document')
    def delete_document(self, document):
        raise RuntimeError('This should never be called!')

    @serialization.freeze_tag('AgencyAgency.get_document')
    def get_document(self, document_id):
        raise RuntimeError('This should never be called!')

    # IJournalKeeper

    def register(self, recorder):
        self.replay.register(recorder)

    # IRecorderNone

    def generate_identifier(self, recorder):
        assert not getattr(self, 'indentifier_generated', False)
        self._identifier_generated = True
        return (self.replay.agent_id, )


class AgencyReplier(log.LogProxy, log.Logger,
                    BaseReplayDummy, StateMachineSpecific):

    def __init__(self, replay):
        log.Logger.__init__(self, replay)
        log.LogProxy.__init__(self, replay)

    @replay.named_side_effect('AgencyReplier.reply')
    def reply(self, reply):
        pass


class AgencyRequester(log.LogProxy, log.Logger,
                      BaseReplayDummy, StateMachineSpecific):

    def __init__(self, replay):
        log.Logger.__init__(self, replay)
        log.LogProxy.__init__(self, replay)

    @replay.named_side_effect('AgencyRequester.request')
    def request(self, request):
        pass


class Interest(log.LogProxy, log.Logger, BaseReplayDummy):

    def __init__(self, replay):
        log.Logger.__init__(self, replay)
        log.LogProxy.__init__(self, replay)

    @replay.named_side_effect('Interest.revoke')
    def revoke(self):
        pass

    @replay.named_side_effect('Interest.bind_to_lobby')
    def bind_to_lobby(self):
        pass


class AgencyContractor(log.LogProxy, log.Logger,
                       BaseReplayDummy, StateMachineSpecific):

    def __init__(self, replay):
        log.Logger.__init__(self, replay)
        log.LogProxy.__init__(self, replay)

    @replay.named_side_effect('AgencyContractor.bid')
    def bid(self, bid):
        pass

    @replay.named_side_effect('AgencyContractor.handover')
    def handover(self, bid):
        pass

    @replay.named_side_effect('AgencyContractor.refuse')
    def refuse(self, refusal):
        pass

    @replay.named_side_effect('AgencyContractor.defect')
    def defect(self, cancellation):
        pass

    @replay.named_side_effect('AgencyContractor.finalize')
    def finalize(self, report):
        pass


class AgencyManager(log.LogProxy, log.Logger,
                    BaseReplayDummy, StateMachineSpecific):

    def __init__(self, replay):
        log.Logger.__init__(self, replay)
        log.LogProxy.__init__(self, replay)

    @replay.named_side_effect('AgencyManager.announce')
    def announce(self, announce):
        pass

    @replay.named_side_effect('AgencyManager.reject')
    def reject(self, bid, rejection=None):
        pass

    @replay.named_side_effect('AgencyManager.grant')
    def grant(self, grants):
        pass

    @replay.named_side_effect('AgencyManager.cancel')
    def cancel(self, reason=None):
        pass

    @replay.named_side_effect('AgencyManager.terminate')
    def terminate(self):
        pass