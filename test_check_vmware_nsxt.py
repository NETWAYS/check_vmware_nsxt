#!/usr/bin/env python3

import unittest
import unittest.mock as mock
import sys

sys.path.append('..')

from check_vmware_nsxt import commandline

class CLITesting(unittest.TestCase):

    def test_commandline(self):
        actual = commandline(['-A', 'api', '-u', 'user', '-p', 'password', '-m', 'alarms'])
        self.assertEqual(actual.username, 'user')
        self.assertEqual(actual.api, 'api')
        self.assertEqual(actual.password, 'password')
        self.assertEqual(actual.mode, 'alarms')
        self.assertFalse(actual.insecure)
        self.assertEqual(actual.max_age, 5)
