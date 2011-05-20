from feat.agents.base import replay, manager, poster, message, recipient
from feat.common import fiber


def add_mapping(agent, prefix, ip):
    """Adds a mapping with a contract.
    It has high latency but gives some kind of guarantee."""
    return _broadcast(agent, AddMappingManager, prefix, ip)


def remove_mapping(agent, prefix, ip):
    """Removes a mapping with a contract.
    It has high latency but gives some kind of guarantee."""
    return _broadcast(agent, RemoveMappingManager, prefix, ip)


def new_mapper(agent):
    """Creates a mapper object on witch add_mapping() and remove_mapping()
    can be called. It uses fire-and-forget notifications so it has a very
    low overhead and latency but a little less guarantees."""
    recp = recipient.Broadcast(MappingUpdatesPoster.protocol_id, 'lobby')
    return agent.initiate_protocol(MappingUpdatesPoster, recp)


class DNSMappingManager(manager.BaseManager):

    announce_timeout = 3

    @replay.immutable
    def initiate(self, state, prefix, ip):
        state.prefix = prefix
        state.ip = ip
        state.medium.announce(message.Announcement())

    @replay.immutable
    def closed(self, state):
        msg = message.Grant()
        msg.payload['prefix'] = state.prefix
        msg.payload['ip'] = state.ip

        state.medium.grant([(bid, msg) for bid in state.medium.get_bids()])

    @replay.entry_point
    def completed(self, state, reports):
        self.log("completed manager")
        report = reports[0]
        return report.payload['suffix'], report.reply_to


class AddMappingManager(DNSMappingManager):
    protocol_id = 'add-dns-mapping'


class RemoveMappingManager(DNSMappingManager):
    protocol_id = 'remove-dns-mapping'


class MappingUpdatesPoster(poster.BasePoster):

    protocol_id = 'update-dns-mapping'

    ### Public Methods ###

    @replay.side_effect
    def add_mapping(self, prefix, ip):
        self.notify("add_mapping", prefix, ip)

    @replay.side_effect
    def remove_mapping(self, prefix, ip):
        self.notify("remove_mapping", prefix, ip)

    ### Overridden Methods ###

    def pack_payload(self, action, prefix, ip):
        return action, (prefix, ip)



### Private Stuff ###


def _broadcast(agent, manager_factory, *args, **kwargs):
    recp = recipient.Broadcast(manager_factory.protocol_id, 'lobby')
    f = fiber.succeed(manager_factory)
    f.add_callback(agent.initiate_protocol, recp, *args, **kwargs)
    f.add_callback(manager_factory.notify_finish)
    return f