#!/usr/bin/env python

import unittest
import unittest.mock as mock
import sys
import os
import datetime
import json

sys.path.append('..')

from check_vmware_nsxt import main
from check_vmware_nsxt import fix_tls_cert_store
from check_vmware_nsxt import commandline
from check_vmware_nsxt import worst_state
from check_vmware_nsxt import time_iso
from check_vmware_nsxt import build_datetime
from check_vmware_nsxt import Client
from check_vmware_nsxt import CriticalException

os.environ["TZ"] = "UTC"

class MainTesting(unittest.TestCase):

    @mock.patch('check_vmware_nsxt.Client')
    def test_main(self, mock_client):

        args = commandline(['-A', 'api', '-u', 'user', '-p', 'password', '-m', 'alarms'])
        main(args)

        mock_client.assert_called_with('api', 'user', 'password', verify=True, max_age=5)

class CLITesting(unittest.TestCase):

    def test_commandline(self):
        actual = commandline(['-A', 'api', '-u', 'user', '-p', 'password', '-m', 'alarms'])
        self.assertEqual(actual.username, 'user')
        self.assertEqual(actual.api, 'api')
        self.assertEqual(actual.password, 'password')
        self.assertEqual(actual.mode, 'alarms')
        self.assertFalse(actual.insecure)
        self.assertEqual(actual.max_age, 5)

    def test_commandline_exclude(self):
        actual = commandline(['-A', 'api', '-u', 'user', '-p', 'password', '-m', 'alarms', '--exclude', 'foo', '--exclude', 'bar'])
        self.assertEqual(actual.exclude, ['foo', 'bar'])

    def test_commandline_fromenv(self):
        os.environ['CHECK_VMWARE_NSXT_API_USER'] = 'GEH'
        os.environ['CHECK_VMWARE_NSXT_API_PASSWORD'] = 'HEIM'

        actual = commandline(['-A', 'api', '-m', 'alarms'])
        self.assertEqual(actual.username, 'GEH')
        self.assertEqual(actual.password, 'HEIM')

        os.unsetenv('CHECK_VMWARE_NSXT_API_USER')
        os.unsetenv('CHECK_VMWARE_NSXT_API_PASSWORD')

class UtilTesting(unittest.TestCase):

    def test_worst_state(self):

        actual = worst_state()
        expected = 3
        self.assertEqual(actual, expected)

        actual = worst_state(0,1,2)
        expected = 2
        self.assertEqual(actual, expected)

        actual = worst_state(1,2,3,4)
        expected = 3
        self.assertEqual(actual, expected)

        actual = worst_state(0,0,0,0)
        expected = 0
        self.assertEqual(actual, expected)

    def test_build_datetime(self):

        actual = build_datetime(1683988760)
        expected = datetime.datetime(1970, 1, 20, 11, 46, 28, 760000)
        self.assertEqual(actual, expected)

    def test_time_iso(self):

        actual = build_datetime(1683988760)
        expected = datetime.datetime(1970, 1, 20, 11, 46, 28, 760000)
        self.assertEqual(actual, expected)

    @mock.patch('os.stat')
    def test_fix_tls_cert_store(self, mock_os):

        self.assertIsNone(fix_tls_cert_store(None))

        m = mock.MagicMock()
        m.st_size = 10
        mock_os.return_value = m

        fix_tls_cert_store("/tmp/foo")

        mock_os.assert_called_with("/tmp/foo")


class ClientTesting(unittest.TestCase):

    @mock.patch('requests.request')
    def test_cluster_status_404(self, mock_req):
        m = mock.MagicMock()
        m.status_code = 404
        mock_req.return_value = m

        c = Client('api', 'username', 'password', logger=None, verify=True, max_age=5)

        with self.assertRaises(CriticalException) as context:
            c.get_cluster_status().print_and_return()

    @mock.patch('requests.request')
    def test_cluster_status_no_json(self, mock_req):
        m = mock.MagicMock()
        m.status_code = 200
        m.json.side_effect = Exception("no json")
        mock_req.return_value = m

        c = Client('api', 'username', 'password', logger=None, verify=True, max_age=5)

        with self.assertRaises(CriticalException) as context:
            c.get_cluster_status().print_and_return()

    @mock.patch('builtins.print')
    @mock.patch('requests.request')
    def test_cluster_status_ok(self, mock_req, mock_print):

        with open('testdata/fixtures/cluster-status.json') as f:
            testdata = json.load(f)

        m = mock.MagicMock()
        m.status_code = 200
        m.json.return_value = testdata
        mock_req.return_value = m

        c = Client('api', 'username', 'password', logger=None, verify=True, max_age=5)

        actual = c.get_cluster_status().print_and_return()
        expected = 0

        self.assertEqual(actual, expected)
        mock_print.assert_called_with("[OK] control_cluster_status=STABLE - mgmt_cluster_status=STABLE - control_cluster_status=STABLE - nodes_online=3\n\n[OK] DATASTORE: STABLE - 3 members\n[OK] CLUSTER_BOOT_MANAGER: STABLE - 3 members\n[OK] CONTROLLER: STABLE - 3 members\n[OK] MANAGER: STABLE - 3 members\n[OK] POLICY: STABLE - 3 members\n[OK] HTTPS: STABLE - 3 members\n[OK] ASYNC_REPLICATOR: STABLE - 3 members\n[OK] MONITORING: STABLE - 3 members\n[OK] IDPS_REPORTING: STABLE - 3 members\n[OK] CORFU_NONCONFIG: STABLE - 3 members\n| nodes_online=3;;;0")

    @mock.patch('builtins.print')
    @mock.patch('requests.request')
    def test_alarms_ok(self, mock_req, mock_print):

        with open('testdata/fixtures/alarms.json') as f:
            testdata = json.load(f)

        m = mock.MagicMock()
        m.status_code = 200
        m.json.return_value = testdata
        mock_req.return_value = m

        c = Client('api', 'username', 'password', logger=None, verify=True, max_age=5)

        actual = c.get_alarms().print_and_return()
        expected = 1

        self.assertEqual(actual, expected)
        mock_print.assert_called_with('[WARNING] 1 alarms - 1 medium\n\n[MEDIUM] (2021-04-26 15:25:18) (node1) Intelligence Health/Storage Latency High - Intelligence node storage latency is high.\n| alarms=1;;;0 alarms.medium=1;;;0')

    @mock.patch('builtins.print')
    @mock.patch('requests.request')
    def test_alarms_exclude(self, mock_req, mock_print):

        with open('testdata/fixtures/alarms.json') as f:
            testdata = json.load(f)

        m = mock.MagicMock()
        m.status_code = 200
        m.json.return_value = testdata
        mock_req.return_value = m

        c = Client('api', 'username', 'password', logger=None, verify=True, max_age=5)

        actual = c.get_alarms(excludes=["M[A-Z]+M"]).print_and_return()
        expected = 0

        self.assertEqual(actual, expected)
        mock_print.assert_called_with('[OK] 1 alarms\n| alarms=1;;;0')

    @mock.patch('builtins.print')
    @mock.patch('requests.request')
    def test_capacity_usage_ok(self, mock_req, mock_print):

        with open('testdata/fixtures/capacity-usage.json') as f:
            testdata = json.load(f)

        m = mock.MagicMock()
        m.status_code = 200
        m.json.return_value = testdata
        mock_req.return_value = m

        c = Client('api', 'username', 'password', logger=None, verify=True, max_age=5)

        actual = c.get_capacity_usage().print_and_return()
        expected = 1

        self.assertEqual(actual, expected)
        mock_print.assert_called_with('[WARNING] 28 info - last update: 2021-04-30 09:17:40 - last update older than 5 minutes\n\n[OK] [INFO] System-wide NAT rules: 0 of 25000 (0%)\n[OK] [INFO] Network Introspection Rules: 1 of 10000 (0.01%)\n[OK] [INFO] System-wide Endpoint Protection Enabled Hosts: 0 of 256 (0%)\n[OK] [INFO] Hypervisor Hosts: 18 of 1024 (1.75%)\n[OK] [INFO] System-wide Firewall Rules: 81 of 100000 (0.08%)\n[OK] [INFO] System-wide DHCP Pools: 0 of 10000 (0%)\n[OK] [INFO] System-wide Edge Nodes: 10 of 320 (3.12%)\n[OK] [INFO] Active Directory Domains (Identity Firewall): 0 of 4 (0%)\n[OK] [INFO] vSphere Clusters Prepared for NSX: 4 of 128 (3.12%)\n[OK] [INFO] Prefix-lists: 20 of 500 (4%)\n[OK] [INFO] Logical Switches: 12 of 10000 (0.12%)\n[OK] [INFO] System-wide Logical Switch Ports: 145 of 25000 (0.58%)\n[OK] [INFO] Active Directory Groups (Identity Firewall): 0 of 100000 (0%)\n[OK] [INFO] Distributed Firewall Rules: 75 of 100000 (0.07%)\n[OK] [INFO] System-wide Endpoint Protection Enabled Virtual Machines: 0 of 7500 (0%)\n[OK] [INFO] Distributed Firewall Sections: 23 of 10000 (0.23%)\n[OK] [INFO] Groups Based on IP Sets: 37 of 10000 (0.37%)\n[OK] [INFO] Edge Clusters: 3 of 160 (1.87%)\n[OK] [INFO] Tier-1 Logical Routers with NAT Enabled: 0 of 4000 (0%)\n[OK] [INFO] System-wide Firewall Sections: 29 of 10000 (0.29%)\n[OK] [INFO] Network Introspection Sections: 1 of 500 (0.2%)\n[OK] [INFO] Groups: 74 of 20000 (0.37%)\n[OK] [INFO] Tier-1 Logical Routers: 4 of 4000 (0.1%)\n[OK] [INFO] IP Sets: 37 of 10000 (0.37%)\n[OK] [INFO] Network Introspection Service Chains: 0 of 24 (0%)\n[OK] [INFO] Network Introspection Service Paths: 0 of 4000 (0%)\n[OK] [INFO] Tier-0 Logical Routers: 2 of 160 (1.25%)\n[OK] [INFO] DHCP Server Instances: 0 of 10000 (0%)\n| number_of_nat_rules=0%;70;100;0;100 number_of_si_rules=0.01%;70;100;0;100 number_of_gi_protected_hosts=0%;70;100;0;100 number_of_prepared_hosts=1.75%;70;100;0;100 number_of_firewall_rules=0.08%;70;100;0;100 number_of_dhcp_ip_pools=0%;70;100;0;100 number_of_edge_nodes=3.12%;70;100;0;100 number_of_active_directory_domains=0%;70;100;0;100 number_of_vcenter_clusters=3.12%;70;100;0;100 number_of_prefix_list=4%;70;100;0;100 number_of_logical_switches=0.12%;70;100;0;100 number_of_logical_ports=0.58%;70;100;0;100 number_of_active_directory_groups=0%;70;100;0;100 number_of_dfw_rules=0.07%;70;100;0;100 number_of_gi_protected_vms=0%;70;100;0;100 number_of_dfw_sections=0.23%;70;100;0;100 number_of_groups_based_on_ip_sets=0.37%;70;100;0;100 number_of_edge_clusters=1.87%;70;100;0;100 number_of_tier1_with_nat_rule=0%;70;100;0;100 number_of_firewall_sections=0.29%;70;100;0;100 number_of_si_sections=0.2%;70;100;0;100 number_of_nsgroup=0.37%;70;100;0;100 number_of_tier1_routers=0.1%;70;100;0;100 number_of_ipsets=0.37%;70;100;0;100 number_of_si_service_chains=0%;70;100;0;100 number_of_si_service_paths=0%;70;100;0;100 number_of_tier0_routers=1.25%;70;100;0;100 number_of_dhcp_servers=0%;70;100;0;100')

    @mock.patch('builtins.print')
    @mock.patch('requests.request')
    def test_capacity_usage_exclude(self, mock_req, mock_print):

        with open('testdata/fixtures/capacity-usage.json') as f:
            testdata = json.load(f)

        m = mock.MagicMock()
        m.status_code = 200
        m.json.return_value = testdata
        mock_req.return_value = m

        c = Client('api', 'username', 'password', logger=None, verify=True, max_age=5)

        actual = c.get_capacity_usage(".*").print_and_return()
        expected = 0
