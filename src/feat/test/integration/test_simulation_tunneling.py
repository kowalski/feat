# F3AT - Flumotion Asynchronous Autonomous Agent Toolkit
# Copyright (C) 2010,2011 Flumotion Services, S.A.
# All rights reserved.

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

# See "LICENSE.GPL" in the source distribution for more information.

# Headers in this file shall remain intact.
from feat.agents.base import agent, descriptor, replay, recipient
from feat.agents.base import collector, poster, dbtools
from feat.agents.base import contractor, manager, message
from feat.agents.shard import shard_agent
from feat.common import defer
from feat.common.text_helper import format_block

from feat.test.integration import common

from feat.interface.protocols import InterestType
from feat.interface.recipient import IRecipient


@descriptor.register("test_agent")
class TestDescriptor(descriptor.Descriptor):
    pass


@agent.register("test_agent")
class TestAgent(agent.BaseAgent):

    @replay.mutable
    def initiate(self, state):
        state.public_notifications = []
        state.private_notifications = []
        state.private_announces = []
        state.private_bids = []
        state.private_grants = []
        state.private_payload = ""

    @replay.immutable
    def enable_interest(self, state):
        state.medium.register_interest(DummyPrivateCollector)
        state.medium.register_interest(DummyPublicCollector)
        state.medium.register_interest(DummyPrivateContractor)

    @replay.immutable
    def disable_interest(self, state):
        state.medium.revoke_interest(DummyPrivateCollector)
        state.medium.revoke_interest(DummyPublicCollector)
        state.medium.revoke_interest(DummyPrivateContractor)

    @replay.immutable
    def enable_tunneling(self, state):
        state.medium.enable_channel("tunnel")

    @replay.immutable
    def disable_tunneling(self, state):
        state.medium.disable_channel("tunnel")

    @replay.immutable
    def post_public_notification(self, state, recipients, payload):
        poster = state.medium.initiate_protocol(DummyPublicPoster, recipients)
        poster.notify(payload)

    @replay.immutable
    def post_private_notification(self, state, recipients, payload):
        poster = state.medium.initiate_protocol(DummyPrivatePoster, recipients)
        poster.notify(payload)

    @replay.immutable
    def start_private_contract(self, state, recipients, payload, expected):
        state.medium.initiate_protocol(DummyPrivateManager, recipients,
                                       payload, expected)

    @replay.mutable
    def reset(self, state):
        state.public_notifications = []
        state.private_notifications = []
        state.private_announces = []
        state.private_bids = []
        state.private_grants = []

    @replay.mutable
    def set_private_payload(self, state, payload):
        state.private_payload = payload

    @replay.immutable
    def get_public_notifications(self, state):
        return list(state.public_notifications)

    @replay.immutable
    def get_private_notifications(self, state):
        return list(state.private_notifications)

    @replay.immutable
    def get_private_announces(self, state):
        return list(state.private_announces)

    @replay.immutable
    def get_private_bids(self, state):
        return list(state.private_bids)

    @replay.immutable
    def get_private_grants(self, state):
        return list(state.private_grants)

    @replay.immutable
    def get_private_payload(self, state):
        return state.private_payload

    ### protected ###

    @replay.mutable
    def _add_public_notification(self, state, payload):
        state.public_notifications.append(payload)

    @replay.mutable
    def _add_private_notification(self, state, payload):
        state.private_notifications.append(payload)

    @replay.mutable
    def _add_private_announce(self, state, payload):
        state.private_announces.append(payload)

    @replay.mutable
    def _add_private_bid(self, state, payload):
        state.private_bids.append(payload)

    @replay.mutable
    def _add_private_grant(self, state, payload):
        state.private_grants.append(payload)


class DummyPrivatePoster(poster.BasePoster):
    protocol_id = 'dummy-private-notification'

    def pack_payload(self, value):
        return value


class DummyPrivateCollector(collector.BaseCollector):

    interest_type = InterestType.private
    protocol_id = 'dummy-private-notification'

    @replay.immutable
    def notified(self, state, message):
        state.agent._add_private_notification(message.payload)


class DummyPublicPoster(poster.BasePoster):
    protocol_id = 'dummy-public-notification'

    def pack_payload(self, value):
        return value


class DummyPublicCollector(collector.BaseCollector):

    interest_type = InterestType.public
    protocol_id = 'dummy-public-notification'

    @replay.immutable
    def notified(self, state, message):
        state.agent._add_public_notification(message.payload)


class DummyPrivateContractor(contractor.BaseContractor):

    protocol_id = 'dummy-private-contract'
    interest_type = InterestType.private

    @replay.immutable
    def announced(self, state, announce):
        state.agent._add_private_announce(announce.payload)
        bid = message.Bid(payload=state.agent.get_private_payload())
        state.medium.bid(bid)

    @replay.immutable
    def rejected(self, state, rejection):
        pass

    @replay.immutable
    def granted(self, state, grant):
        state.agent._add_private_grant(grant.payload)


class DummyPrivateManager(manager.BaseManager):

    protocol_id = 'dummy-private-contract'

    initiate_timeout = 10
    grant_timeout = 10

    @replay.mutable
    def initiate(self, state, payload, expected):
        state.medium.announce(message.Announcement(payload=payload))
        state.expected = expected
        state.bids = []

    @replay.mutable
    def bid(self, state, bid):
        state.agent._add_private_bid(bid.payload)
        state.bids.append(bid)

    @replay.mutable
    def closed(self, state):
        for bid in state.bids:
            if bid.payload == state.expected:
                payload = state.agent.get_private_payload()
                grant = message.Grant(payload=payload)
                state.medium.grant((bid, grant, ))
                return


@common.attr(timescale=0.05)
class TunnellingTest(common.SimulationTest):

    def setUp(self):
        config = shard_agent.ShardAgentConfiguration(doc_id = 'test-config',
                                                     hosts_per_shard = 2)
        dbtools.initial_data(config)
        self.override_config('shard_agent', config)
        return common.SimulationTest.setUp(self)

    @defer.inlineCallbacks
    def prolog(self):
        setup = format_block("""
        agency1 = spawn_agency()
        agency1.disable_protocol('setup-monitoring', 'Task')
        ha1m = agency1.start_agent(descriptor_factory('host_agent'))
        ha1 = ha1m.get_agent()

        wait_for_idle(20)

        agency2 = spawn_agency()
        agency2.disable_protocol('setup-monitoring', 'Task')
        ha2m = agency2.start_agent(descriptor_factory('host_agent'))
        ha2 = ha2m.get_agent()

        wait_for_idle(20)

        agency3 = spawn_agency()
        agency3.disable_protocol('setup-monitoring', 'Task')
        ha3m = agency3.start_agent(descriptor_factory('host_agent'))
        ha3 = ha3m.get_agent()

        wait_for_idle(20)

        ha1.start_agent(descriptor_factory('test_agent'))
        ha1.start_agent(descriptor_factory('test_agent'))
        ha2.start_agent(descriptor_factory('test_agent'))
        ha2.start_agent(descriptor_factory('test_agent'))
        ha3.start_agent(descriptor_factory('test_agent'))
        ha3.start_agent(descriptor_factory('test_agent'))
        """)

        yield self.process(setup)

        self.ha1 = self.get_local('ha1')
        self.ha2 = self.get_local('ha2')
        self.ha3 = self.get_local('ha3')

    def testValidateProlog(self):
        iter_agents = self.driver.iter_agents
        self.assertEqual(3, len(list(iter_agents("host_agent"))))
        self.assertEqual(2, len(list(iter_agents("shard_agent"))))
        self.assertEqual(6, len(list(iter_agents("test_agent"))))

    ### Tunneling backend tests ###

    @defer.inlineCallbacks
    def testTunnelingBackendContracts(self):
        a1, a2 = self.get_host_agents("test_agent", self.ha1)
        a3, a4 = self.get_host_agents("test_agent", self.ha2)
        a5, a6 = self.get_host_agents("test_agent", self.ha3)

        agents = [a1, a2, a3, a4, a5, a6]
        payloads = ["spam", "bacon", "egg", "tomato", "sausage", "beans"]
        recipients = []

        for a, n in zip(agents, payloads):
            a.set_private_payload(n)

        for a in agents:
            # Agent must have a channel to be able
            # to get it's address through it
            a.enable_tunneling()
            recipients.append(a.get_own_address("tunnel"))
            a.disable_tunneling()

        a1.start_private_contract(recipients, "spam", "tomato")
        yield self.wait_for_idle(20)
        self.check_private_contract(agents, [([], [], [])]*6)
        self.full_reset()

        agents[1].enable_interest()
        agents[2].enable_interest()
        agents[3].enable_interest()
        agents[5].enable_interest()

        a1.start_private_contract(recipients, "spam", "tomato")
        yield self.wait_for_idle(20)
        self.check_private_contract(agents, [([], [], [])]*6)
        self.full_reset()

        agents[0].enable_tunneling()
        agents[1].enable_tunneling()
        agents[3].enable_tunneling()
        agents[5].enable_tunneling()

        a1.start_private_contract(recipients, "spam", "tomato")
        yield self.wait_for_idle(20)
        self.check_private_contract(agents,
                                    [([], ["bacon", "beans", "tomato"], []),
                                     (["spam"], [], []),
                                     ([], [], []),
                                     (["spam"], [], ["spam"]),
                                     ([], [], []),
                                     (["spam"], [], [])])
        self.full_reset()

        agents[0].enable_interest()
        agents[1].disable_interest()
        agents[2].enable_interest()
        agents[3].disable_interest()
        agents[4].enable_interest()

        a4.start_private_contract(recipients, "more spam", "beans")
        yield self.wait_for_idle(20)
        self.check_private_contract(agents,
                                    [(["more spam"], [], []),
                                     ([], [], []),
                                     ([], [], []),
                                     ([], ["beans", "spam"], []),
                                     ([], [], []),
                                     (["more spam"], [], ["tomato"])])
        self.full_reset()

    @defer.inlineCallbacks
    def testMixedBackendContracts(self):
        a1, a2 = self.get_host_agents("test_agent", self.ha1)
        a3, a4 = self.get_host_agents("test_agent", self.ha2)
        a5, a6 = self.get_host_agents("test_agent", self.ha3)

        agents = [a1, a2, a3, a4, a5, a6]
        payloads = ["spam", "bacon", "egg", "tomato", "sausage", "beans"]
        default_recipients = []
        tunnel_recipients = []

        for a, n in zip(agents, payloads):
            a.set_private_payload(n)

        for a in agents:
            # Agent must have a channel to be able
            # to get it's address through it
            a.enable_tunneling()
            tunnel_recipients.append(a.get_own_address("tunnel"))
            default_recipients.append(a.get_own_address())
            a.disable_tunneling()

        for a in agents:
            a.enable_interest()
            a.enable_tunneling()

        tr = tunnel_recipients
        dr = default_recipients
        mixed_recipients = [dr[0], dr[1], tr[2], tr[3], dr[4], tr[5]]
        a3.start_private_contract(mixed_recipients, "lovely spam", "sausage")
        yield self.wait_for_idle(20)
        self.check_private_contract(agents,
                                    [(["lovely spam"], [], []),
                                     (["lovely spam"], [], []),
                                     (["lovely spam"], ["bacon", "beans",
                                                        "egg", "sausage",
                                                        "spam", "tomato"], []),
                                     (["lovely spam"], [], []),
                                     (["lovely spam"], [], ["egg"]),
                                     (["lovely spam"], [], [])])
        self.full_reset()

    @defer.inlineCallbacks
    def testTunnelingBackendDirectNotifications(self):
        a1, a2 = self.get_host_agents("test_agent", self.ha1)
        a3, a4 = self.get_host_agents("test_agent", self.ha2)
        a5, a6 = self.get_host_agents("test_agent", self.ha3)

        agents = [a1, a2, a3, a4, a5, a6]
        recipients = []

        for a in agents:
            a.enable_tunneling()
            recipients.append(a.get_own_address("tunnel"))
            a.disable_tunneling()

        a1.post_private_notification(recipients, "spam")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [[]]*6)
        self.full_reset()

        for a in agents:
            a.enable_interest()

        a1.post_private_notification(recipients, "spam")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [[]]*6)
        self.full_reset()

        for a in (a1, a4, a5):
            a.enable_tunneling()

        a1.post_private_notification(recipients, "bacon")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [["bacon"], [], [],
                                                 ["bacon"], ["bacon"], []])
        self.full_reset()

        for a in (a1, a4, a5):
            a.disable_tunneling()

        for a in (a2, a3, a6):
            a.enable_tunneling()

        # a1 disabled the channel, nothing will got through
        a1.post_private_notification(recipients, "eggs")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [[]]*6)
        self.full_reset()

        # a2 is enabled so everything should be fine
        a2.post_private_notification(recipients, "eggs")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [[], ["eggs"], ["eggs"],
                                                 [], [], ["eggs"]])
        self.full_reset()

        for a in (a1, a4, a5):
            a.enable_tunneling()

        a6.post_private_notification(recipients, "tomato")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [["tomato"], ["tomato"],
                                                 ["tomato"], ["tomato"],
                                                 ["tomato"], ["tomato"]])
        self.full_reset()

        for a in (a2, a3, a5):
            a.disable_interest()

        a5.post_private_notification(recipients, "sausage")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [["sausage"], [],
                                                 [], ["sausage"],
                                                 [], ["sausage"]])
        self.full_reset()

        for a in (a2, a3, a5):
            a.enable_interest()

        r = recipients

        a1.post_private_notification([r[1], r[3], r[5]], "more spam")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [[], ["more spam"],
                                                 [], ["more spam"],
                                                 [], ["more spam"]])
        self.full_reset()

        a3.post_private_notification([r[0], r[2], r[4]], "lovely spam")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [["lovely spam"], [],
                                                 ["lovely spam"], [],
                                                 ["lovely spam"], []])
        self.full_reset()

    ### Default backend tests for reference ###

    @defer.inlineCallbacks
    def testDefaultBackendDirectNotifications(self):
        a1, a2 = self.get_host_agents("test_agent", self.ha1)
        a3, a4 = self.get_host_agents("test_agent", self.ha2)
        a5, a6 = self.get_host_agents("test_agent", self.ha3)

        agents = [a1, a2, a3, a4, a5, a6]
        recipients = []

        for a in agents:
            recipients.append(IRecipient(a))

        a1.post_public_notification(recipients, "foo")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[]]*6)
        self.full_reset()

        for a in (a1, a4, a6):
            a.enable_interest()

        a1.post_public_notification(recipients, "foo")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["foo"], [], [],
                                                 ["foo"], [], ["foo"]])
        self.full_reset()

        for a in (a1, a4, a6):
            a.disable_interest()

        for a in (a2, a3, a5):
            a.enable_interest()

        a1.post_public_notification(recipients, "bar")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[], ["bar"], ["bar"],
                                                 [], ["bar"], []])
        self.full_reset()

        for a in (a1, a4, a6):
            a.enable_interest()

        a1.post_private_notification(recipients, "spam")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [["spam"]]*6)
        self.full_reset()

        r = recipients

        a1.post_private_notification([r[1], r[3], r[5]], "bacon")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [[], ["bacon"]]*3)
        self.full_reset()

        a4.post_private_notification(recipients, "egg")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [["egg"]]*6)
        self.full_reset()

        a4.post_private_notification([r[1], r[3], r[5]], "beans")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [[], ["beans"]]*3)
        self.full_reset()

        a5.post_private_notification(recipients, "tomato")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [["tomato"]]*6)
        self.full_reset()

        a5.post_private_notification([r[1], r[3], r[5]], "more spam")
        yield self.wait_for_idle(20)
        self.check_private_notification(agents, [[], ["more spam"]]*3)
        self.full_reset()

        a1.post_public_notification(recipients, "sausage")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["sausage"]]*6)
        self.full_reset()

        a1.post_public_notification([r[1], r[3], r[5]], "and spam")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[], ["and spam"]]*3)
        self.full_reset()

        a4.post_public_notification(recipients, "baked beans")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["baked beans"]]*6)
        self.full_reset()

        a4.post_public_notification([r[1], r[3], r[5]], "with spam")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[], ["with spam"]]*3)
        self.full_reset()

        a5.post_public_notification(recipients, "fried egg")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["fried egg"]]*6)
        self.full_reset()

        a5.post_public_notification([r[1], r[3], r[5]], "lovely spam")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[], ["lovely spam"]]*3)
        self.full_reset()

    @defer.inlineCallbacks
    def testDefaultBackendBroadcastNotifications(self):
        a1, a2 = self.get_host_agents("test_agent", self.ha1)
        a3, a4 = self.get_host_agents("test_agent", self.ha2)
        a5, a6 = self.get_host_agents("test_agent", self.ha3)

        agents = [a1, a2, a3, a4, a5, a6]

        pid = DummyPublicCollector.protocol_id
        s1 = recipient.Broadcast(pid, a1.get_shard_id())
        s2 = recipient.Broadcast(pid, a5.get_shard_id())

        recipients = [s1, s2]

        a1.post_public_notification(recipients, "foo")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[]]*6)
        self.full_reset()

        for a in (a1, a4, a6):
            a.enable_interest()

        a1.post_public_notification(recipients, "foo")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["foo"], [], [],
                                                ["foo"], [], ["foo"]])
        self.full_reset()

        for a in (a1, a4, a6):
            a.disable_interest()

        for a in (a2, a3, a5):
            a.enable_interest()

        a1.post_public_notification(recipients, "bar")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[], ["bar"], ["bar"],
                                                [], ["bar"], []])
        self.full_reset()

        for a in (a1, a4, a6):
            a.enable_interest()

        a1.post_public_notification(s1, "spam")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["spam"], ["spam"], ["spam"],
                                                ["spam"], [], []])
        self.full_reset()

        a1.post_public_notification(s2, "bacon")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[], [], [],
                                                [], ["bacon"], ["bacon"]])
        self.full_reset()

        a6.post_public_notification(s1, "and spam")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["and spam"], ["and spam"],
                                                ["and spam"], ["and spam"],
                                                [], []])
        self.full_reset()

        a6.post_public_notification(s2, "with eggs")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[], [], [], [],
                                                ["with eggs"], ["with eggs"]])
        self.full_reset()

    @defer.inlineCallbacks
    def testDefaultBackendMixedNotifications(self):
        a1, a2 = self.get_host_agents("test_agent", self.ha1)
        a3, a4 = self.get_host_agents("test_agent", self.ha2)
        a5, a6 = self.get_host_agents("test_agent", self.ha3)

        agents = [a1, a2, a3, a4, a5, a6]
        dr = []

        for a in agents:
            dr.append(IRecipient(a))

        pid = DummyPublicCollector.protocol_id
        s1 = recipient.Broadcast(pid, a1.get_shard_id())
        s2 = recipient.Broadcast(pid, a5.get_shard_id())

        br = [s1, s2]

        for a in (a1, a2, a3, a4, a6):
            a.enable_interest()

        a1.post_public_notification([dr[1], br[0], dr[4]], "spam")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["spam"], ["spam"], ["spam"],
                                                ["spam"], [], []])
        self.full_reset()

        a1.post_public_notification([br[1], dr[0], dr[4]], "bacon")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["bacon"], [], [],
                                                [], [], ["bacon"]])
        self.full_reset()

        a6.post_public_notification([dr[0], dr[5], br[0]], "egg")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [["egg"], ["egg"], ["egg"],
                                                ["egg"], [], ["egg"]])
        self.full_reset()

        a1.post_public_notification([br[1], dr[3], dr[4]], "sausage")
        yield self.wait_for_idle(20)
        self.check_public_notification(agents, [[], [], [],
                                                ["sausage"], [], ["sausage"]])
        self.full_reset()

    ### private ###

    def check_private_contract(self, agents, expected):
        for a, (announces, bids, grants) in zip(agents, expected):
            self.assertEqual(sorted(a.get_private_announces()), announces)
            self.assertEqual(sorted(a.get_private_bids()), bids)
            self.assertEqual(sorted(a.get_private_grants()), grants)

    def check_private_notification(self, agents, expected):
        for a, notifications in zip(agents, expected):
            self.assertEqual(a.get_private_notifications(), notifications)

    def check_public_notification(self, agents, expected):
        for a, notifications in zip(agents, expected):
            self.assertEqual(a.get_public_notifications(), notifications)

    def full_reset(self):
        a1, a2 = self.get_host_agents("test_agent", self.ha1)
        a3, a4 = self.get_host_agents("test_agent", self.ha2)
        a5, a6 = self.get_host_agents("test_agent", self.ha3)

        a1.reset()
        a2.reset()
        a3.reset()
        a4.reset()
        a5.reset()
        a6.reset()

    def get_agents(self, type_name):
        return list(self.driver.iter_agents(type_name))

    def get_host_agents(self, type_name, host):
        result = []
        for m in self.get_agents(type_name):
            a = m.get_agent()
            hosts = a.query_partners_with_role("all", "host")
            if not hosts:
                continue
            if hosts[0].recipient == IRecipient(host):
                result.append(a)
        if not result:
            self.fail("Agent not found for host %s" % host)
        return result

    def mk_tunnel_recipient(self, agent):
        # Verry hacky...
        medium = agent._get_state().medium
        backend = medium.agency._backends["tunnel"]
        key = agent.get_agent_id()
        route = backend.route
        return recipient.Recipient(key, route, backend.channel_type)
