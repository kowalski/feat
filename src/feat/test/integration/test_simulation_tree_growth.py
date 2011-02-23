# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
from twisted.internet import defer
from twisted.trial.unittest import FailTest

from feat.common import delay
from feat.common.text_helper import format_block
from feat.test.integration import common
from feat.agents.host import host_agent
from feat.agents.shard import shard_agent
from feat.agents.base import recipient


class Shard(object):

    def __init__(self, name):
        self.name = name
        self.agents = list()
        self.children = list()

    # def count_agents(self):
    #     res = dict()
    #     for agent in self.agents:
    #         factory = agent.get_agent().__class__.__name__
    #         if factory in res:
    #             res[factory] += 1
    #         else:
    #             res[factory] = 1
    #     return res

    def pick_agent_by_type(self, factory):
        try:
            return next(self.iter_agents_by_type(factory))
        except StopIteration:
            return None

    def pick_agents_by_type(self, factory):
        return [x for x in self.iter_agents_by_type(factory)]

    def iter_agents_by_type(self, factory):
        for x in self.agents:
            if isinstance(x.get_agent(), factory):
                yield x


class Common(object):

    def assert_all_agents_in_shard(self, agency, shard):
        for agent in agency._agents:
            desc = agent.get_descriptor()
            self.assertEqual(shard, desc.shard, str(type(agent.agent)))

    def get_topology(self):
        return self.scan_shard('root')

    def scan_shard(self, name):
        res = Shard(name)
        res.agents = self.find_agents(name)
        shard_a = res.pick_agent_by_type(shard_agent.ShardAgent)
        for partner in shard_a.get_agent().query_partners('children'):
            res.children.append(self.scan_shard(partner.recipient.shard))
        return res

    def find_agents(self, shard):
        return [x for x in self.driver.iter_agents() \
                if x._descriptor.shard == shard]


@common.attr('slow')
class FailureRecoverySimulation(common.SimulationTest, Common):

    start_host_agent = format_block("""
        spawn_agency()
        _.start_agent(descriptor_factory('host_agent'))
        """)

    def prolog(self):
        setup = format_block("""
        agency = spawn_agency()
        shard_desc = descriptor_factory('shard_agent', 'root')
        agency.start_agent(descriptor_factory('host_agent'), bootstrap=True)
        agent = _.get_agent()
        agent.start_agent(shard_desc, children=2, hosts=2)

        spawn_agency()
        _.start_agent(descriptor_factory('host_agent'))

        # First 1 lvl child shard

        spawn_agency()
        _.start_agent(descriptor_factory('host_agent'))

        spawn_agency()
        _.start_agent(descriptor_factory('host_agent'))

        # Second 1 lvl child shard

        spawn_agency()
        _.start_agent(descriptor_factory('host_agent'))

        spawn_agency()
        _.start_agent(descriptor_factory('host_agent'))

        # First 2 lvl child shard

        spawn_agency()
        _.start_agent(descriptor_factory('host_agent'))

        spawn_agency()
        _.start_agent(descriptor_factory('host_agent'))

        """)
        return self.process(setup)

    def testValidateProlog(self):
        topology = self.get_topology()

        def validate(shard, lvl):
            self.info('Validating shard %s on lvl %d', shard.name, lvl)
            self.info('Agents: %r', [x.get_agent() for x in shard.agents])
            self.assertEqual(3, len(shard.agents))
            self.assertEqual(
                1, len(shard.pick_agents_by_type(shard_agent.ShardAgent)))
            self.assertEqual(
                2, len(shard.pick_agents_by_type(host_agent.HostAgent)))
            if lvl == 0:
                self.assertEqual(2, len(shard.children))
            elif lvl == 1:
                self.assertTrue(len(shard.children) in (0, 1))
            elif lvl == 2:
                self.assertEqual(0, len(shard.children))
            else:
                raise FailTest('third lvl?')

            for child in shard.children:
                validate(child, lvl+1)

        validate(topology, 0)


@common.attr('slow')
class TreeGrowthSimulation(common.SimulationTest, Common):

    # Timeout is intentionaly set to high. Some of theese tests take a lot
    # of time running with --coverage on buildbot (virtualized machine)
    timeout = 100
    hosts_per_shard = 10
    children_per_shard = 2

    start_host_agent = format_block("""
        a = spawn_agency()
        a.start_agent(descriptor_factory('host_agent'))
        """)

    def prolog(self):
        delay.time_scale = 0.5
        setup = format_block("""
        agency = spawn_agency()
        shard_desc = descriptor_factory('shard_agent', 'root')
        host_desc = descriptor_factory('host_agent')
        d = async agency.start_agent(host_desc)
        agency.start_agent(shard_desc)
        yield d
        agency.snapshot_agents()
        """)
        return self.process(setup)

    def testValidateProlog(self):
        agency = self.get_local('agency')
        self.assertEqual(2, len(agency._agents))
        shard = self._get_root_shard()
        self.assertIsInstance(agency._agents[0].agent, host_agent.HostAgent)
        self.assert_all_agents_in_shard(agency, 'root')
        self._assert_allocated(shard, 'hosts', 1)

    @defer.inlineCallbacks
    def testFillUpTheRootShard(self):
        shard_a = self._get_root_shard()
        for i in range(2, self.hosts_per_shard + 1):
            yield self.process(self.start_host_agent)
            self.assertEqual(i,
                    shard_a._get_state().resources.allocated()['hosts'])

        self.assertEqual(self.hosts_per_shard, len(self.driver._agencies))
        for agency in self.driver._agencies[1:]:
            self.assert_all_agents_in_shard(agency, 'root')
        self.assertEqual(10,
                         shard_a._get_state().resources.allocated()['hosts'])

    @defer.inlineCallbacks
    def testStartNewShard(self):
        fillup_root_shard = self.start_host_agent * (self.hosts_per_shard - 1)
        yield self.process(fillup_root_shard)
        yield self.process(self.start_host_agent)

        last_agency = self.driver._agencies[-1]
        self.assertEqual(2, len(last_agency._agents))
        self.assertIsInstance(last_agency._agents[0].agent,
                              host_agent.HostAgent)
        self.assertIsInstance(last_agency._agents[1].agent,
                              shard_agent.ShardAgent)
        host = last_agency._agents[0]
        shard_a = last_agency._agents[1].agent
        shard = (host.get_descriptor()).shard
        self.assert_all_agents_in_shard(last_agency, shard)
        self._assert_allocated(shard_a, 'hosts', 1)
        self._assert_allocated(shard_a, 'children', 0)

        root_shard = self.driver._agencies[0]._agents[1].agent
        self._assert_allocated(root_shard, 'children', 1)

    @defer.inlineCallbacks
    def testStartLevel2(self):
        # fill all the places in root shard, on shard lvl 1
        # and create the first hosts on lvl 2
        number_of_hosts_to_start =\
            ((self.children_per_shard + 1) * self.hosts_per_shard)

        script = self.start_host_agent * number_of_hosts_to_start
        yield self.process(script)

        root_shard_agencies = self.driver._agencies[0:self.hosts_per_shard]
        for agency in root_shard_agencies:
            self.assert_all_agents_in_shard(agency, 'root')

        # validate root shard
        root_shard = self._get_root_shard()
        root_shard_desc = root_shard.get_descriptor()
        self._assert_allocated(root_shard, 'hosts', 10)
        self._assert_allocated(root_shard, 'children', 2)

        lvl1_shards = root_shard.query_partners('children')
        self.assertEqual(2, len(lvl1_shards))

        # validate lvl 1
        for child in lvl1_shards:
            self.assertIsInstance(child, shard_agent.ChildShardPartner)
            shard_desc = yield self.driver.get_document(child.recipient.key)
            shard_a = self.driver.find_agent(shard_desc.doc_id).get_agent()
            self._assert_allocated(shard_a, 'hosts', 10)

            parent = shard_a.query_partners('parent')
            self.assertIsInstance(parent, shard_agent.ParentShardPartner)
            self.assertEqual(parent.recipient.key, root_shard_desc.doc_id)
            self.assertEqual(parent.recipient.shard, root_shard_desc.shard)

            for host in shard_a.query_partners('hosts'):
                self.assertIsInstance(host, shard_agent.HostPartner)
                host_desc = yield self.driver.get_document(host.recipient.key)
                self.assertEqual(host_desc.shard, shard_desc.shard)
                self.assertEqual(host.recipient.shard, shard_desc.shard)

                host_agency = self.driver.find_agency(host.recipient.key)
                self.assertTrue(host_agency is not None)
                self.assert_all_agents_in_shard(host_agency,
                                                host.recipient.shard)

        #validate last agency (on lvl 2)
        agency = self.driver._agencies[-1]
        self.assertEqual(2, len(agency._agents))
        self.assertIsInstance(agency._agents[0].agent,
                              host_agent.HostAgent)
        shard_a = agency._agents[1].agent
        self.assertIsInstance(shard_a, shard_agent.ShardAgent)
        self._assert_allocated(shard_a, 'hosts', 1)
        self._assert_allocated(shard_a, 'children', 0)

        parent = shard_a.query_partners('parent')
        host = shard_a.query_partners('hosts')
        self.assertEqual(1, len(host))
        self.assertEqual('host', host[0].role)
        self.assertIsInstance(parent, shard_agent.ParentShardPartner)

    @defer.inlineCallbacks
    def testFillupTwoShards(self):
        fillup_two_shards = self.start_host_agent *\
                            (2 * self.hosts_per_shard - 1)
        yield self.process(fillup_two_shards)

        root_shard = self._get_root_shard()
        self._assert_allocated(root_shard, 'hosts', 10)
        self._assert_allocated(root_shard, 'children', 1)

        agencies_for_second_shard = \
            self.driver._agencies[self.hosts_per_shard:]
        shard_a = agencies_for_second_shard[0]._agents[1].agent
        self.assertIsInstance(shard_a, shard_agent.ShardAgent)
        shard = shard_a.get_descriptor().shard
        for agency in agencies_for_second_shard:
            self.assert_all_agents_in_shard(agency, shard)

        self._assert_allocated(shard_a, 'hosts', 10)
        self._assert_allocated(shard_a, 'children', 0)

    def _get_root_shard(self):
        a = self.get_local('agency')._agents[1].agent
        self.assertIsInstance(a, shard_agent.ShardAgent)
        return a

    def _assert_allocated(self, agent, resource, expected):
        resources = agent._get_state().resources
        self.assertEqual(expected,
                         resources.allocated()[resource],
                         resources._get_state().allocations.values())
        from_desc = agent.get_descriptor().allocations
        self.assertEqual(expected,
                         resources.allocated(None, from_desc)[resource],
                         "Allocations in desc: %r" % from_desc)


@common.attr('slow')
class SimulationHostBeforeShard(common.SimulationTest, Common):

    timeout = 100

    def prolog(self):
        pass

    @defer.inlineCallbacks
    def testHATakesShardAgentFromPartnersNotContract(self):
        '''
        In this test case no contract is actually run. This tests the
        scenarion of HA after restart.
        '''

        yield self.driver.process(format_block("""
        agency = spawn_agency()
        desc = descriptor_factory('host_agent')
        """))
        agency = self.get_local('agency')
        desc = self.get_local('desc')
        shard_recp = recipient.Agent('some shard', 'some shard')
        desc.partners = [
            host_agent.ShardPartner(shard_recp)]

        yield self.driver.process("agent = agency.start_agent(desc)\n")
        self.assert_all_agents_in_shard(agency, 'some shard')

    @defer.inlineCallbacks
    def testHAKeepsTillShardAgentAppears(self):
        delay.time_scale = 0.1

        setup = format_block("""
        agency = spawn_agency()
        host_desc = descriptor_factory('host_agent')
        ha = agency.start_agent(host_desc)
        """)
        d = self.process(setup)
        agency = self.get_local('agency')
        ha = agency._agents[0]

        self.assertEqual(1, len(ha._retrying_protocols))
        # check the retries 3 times
        yield self.cb_after(None, ha, 'initiate_protocol')
        self.info('First contract failed.')
        yield self.cb_after(None, ha, 'initiate_protocol')
        yield self.cb_after(None, ha, 'initiate_protocol')

        script = format_block("""
        shard_desc = descriptor_factory('shard_agent', 'root')
        agency = spawn_agency()
        agency.start_agent(shard_desc)
        """)
        # get additional parser - the original is locked in initiated
        # host agent
        parser = self.driver.get_additional_parser()
        parser.dataReceived(script)

        # after shard agent has appeared it is possible to finish
        # initializing the host agent
        yield d

        self.assertEqual(0, len(ha._retrying_protocols))
        self.assertEqual(1, len(agency._agents))
        self.assertIsInstance(agency._agents[0].agent, host_agent.HostAgent)
        self.assert_all_agents_in_shard(agency, 'root')