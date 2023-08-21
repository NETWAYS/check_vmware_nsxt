#!/usr/bin/env python
# coding:utf-8
"""
Icinga check plugin for VMware NSX-T

Supported Modes:

* cluster-status - retrieves the overall NSX-T cluster status from the API
* alarms - Retrieve and display open alarms from the API
* capacity-usage - Retrieves and checks capacity indicators from the API

General API Documentation: https://code.vmware.com/apis/1083/nsx-t

---

VMware NSX® is a trademark of VMware, Inc.

Copyright (C) 2021 NETWAYS GmbH <info@netways.de>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import os
import sys
import argparse
import logging
import datetime
import ssl
import re
from urllib.parse import urljoin
import urllib3
import requests
from requests.auth import HTTPBasicAuth


__version__ = '0.2.0'

OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

STATES = {
    OK: "OK",
    WARNING: "WARNING",
    CRITICAL: "CRITICAL",
    UNKNOWN: "UNKNOWN",
}


def fix_tls_cert_store(cafile_path):
    """
    Ensure we are using the system certstore by default

    See https://github.com/psf/requests/issues/2966
    Inspired by https://github.com/psf/requests/issues/2966#issuecomment-614323746
    """

    # Check if we got a CA file path
    if not cafile_path:
        return

    # If CA file contains something, set as default
    if os.stat(cafile_path).st_size > 0:
        requests.utils.DEFAULT_CA_BUNDLE_PATH = cafile_path
        requests.adapters.DEFAULT_CA_BUNDLE_PATH = cafile_path


class CriticalException(Exception):
    """
    Provide an exception that will cause the check to exit critically with an error
    """


class Client:
    """
    Simple API client for VMware NSX-T
    """

    API_PREFIX = '/api/v1/'

    def __init__(self, api, username, password, logger=None, verify=True, max_age=5):
        self.api = api
        self.username = username
        self.password = password
        self.verify = verify
        self.max_age = max_age

        if logger is None:
            logger = logging.getLogger()

        self.logger = logger

    def request(self, url, method='GET'):
        """
        Basic JSON request handling

        Handles authentication and returns the JSON result when successful
        """

        base_url = urljoin(self.api, self.API_PREFIX)
        request_url = urljoin(base_url, url)

        self.logger.debug("starting API %s request from: %s", method, url)

        try:
            response = requests.request(method, request_url, auth=HTTPBasicAuth(self.username, self.password), verify=self.verify, timeout=10)
        except requests.exceptions.RequestException as req_exc:
            raise CriticalException(req_exc) # pylint: disable=raise-missing-from

        if response.status_code != 200:
            # TODO What about 300 Redirects?
            raise CriticalException('Request to %s was not successful: %s' % (request_url, response.status_code))

        try:
            return response.json()
        except Exception as json_exc:
            raise CriticalException('Could not decode API JSON: ' + str(json_exc)) # pylint: disable=raise-missing-from

    def get_cluster_status(self, excludes=None):
        """
        GET and build ClusterStatus
        """
        return ClusterStatus(self.request('cluster/status'), excludes)

    def get_alarms(self, excludes=None):
        """
        GET and build Alarms
        """
        status = "OPEN"
        # status = "RESOLVED" # for testing
        result = self.request('alarms?page_size=100&status=%s&sort_ascending=false' % status)
        return Alarms(data=result['results'], excludes=excludes)

    def get_capacity_usage(self, excludes=None):
        """
        GET and build CapacityUsage
        """
        return CapacityUsage(self.request('capacity/usage'), self.max_age, excludes)


class CheckResult:
    """
    CheckResult class, stores output, perfdata and state
    """
    def __init__(self):
        self.state = -1
        self.summary = []
        self.output = []
        self.perfdata = []

    def build_output(self):
        raise NotImplementedError("build_output not implemented in %s" % type(self))

    def get_output(self):
        if len(self.summary) == 0:
            self.build_output()
        if self.state < 0:
            self.build_status()

        output = ' - '.join(self.summary)
        if len(self.output) > 0:
            output += "\n\n" + "\n".join(self.output)
        if len(self.perfdata) > 0:
            output += "\n| " + " ".join(self.perfdata)

        try:
            state = STATES[self.state]
        except KeyError:
            state = "UNKNOWN"

        return "[%s] " % state + output

    def build_status(self):
        raise NotImplementedError("build_status not implemented in %s" % type(self))

    def get_status(self):
        if self.state < 0:
            self.build_status()
        if self.state < 0:
            return UNKNOWN

        return self.state

    def print_and_return(self):
        print(self.get_output())
        return self.get_status()


class ClusterStatus(CheckResult):
    """
    See API Documentation: https://code.vmware.com/apis/1083/nsx-t
    https://vdc-download.vmware.com/vmwb-repository/dcr-public/787988e9-6348-4b2a-8617-e6d672c690ee/a187360c-77d5-4c0c-92a8-8e07aa161a27/api_includes/method_ReadClusterStatus.html
    """

    def __init__(self, data, excludes):
        super().__init__()
        self.data = data
        self.excludes = excludes
        if excludes is None:
            self.excludes = []

    def build_output(self):
        for area in ['control_cluster_status', 'mgmt_cluster_status', 'control_cluster_status']:
            self.summary.append(area + '=' + self.data[area]['status'])

        nodes_online = len(self.data['mgmt_cluster_status']['online_nodes'])
        self.summary.append("nodes_online=%d" % nodes_online)
        self.perfdata.append("nodes_online=%d;;;0" % nodes_online)

        for group in self.data['detailed_cluster_status']['groups']:
            state = "OK" if self.data[area]['status'] == "STABLE" else "CRITICAL"
            self.output.append('[%s] %s: %s - %d members' % (state, group['group_type'], group['group_status'], len(group['members'])))

    def build_status(self):
        states = []

        for area in ['control_cluster_status', 'mgmt_cluster_status', 'control_cluster_status']:
            states.append(OK if self.data[area]['status'] == "STABLE" else CRITICAL)

        self.state = worst_state(*states)


class Alarms(CheckResult):
    """
    See API Documentation: https://code.vmware.com/apis/1083/nsx-t
    https://vdc-download.vmware.com/vmwb-repository/dcr-public/787988e9-6348-4b2a-8617-e6d672c690ee/a187360c-77d5-4c0c-92a8-8e07aa161a27/api_includes/method_GetAlarms.html
    """

    def __init__(self, data, excludes):
        super().__init__()
        self.data = data
        self.excludes = excludes
        if excludes is None:
            self.excludes = []

    def _is_excluded(self, alarm):
        # to exclude via --exclude
        identifier = "%s %s %s %s" % (
            alarm['severity'],
            alarm['node_display_name'],
            alarm['feature_display_name'],
            alarm['event_type_display_name'])
        for exclude in self.excludes:
            regexp = re.compile(exclude)
            if bool(regexp.search(identifier)):
                return True
        return False

    def build_output(self):
        states = {}

        for alarm in self.data:
            if self._is_excluded(alarm):
                continue

            severity = alarm['severity']
            if severity in states:
                states[severity] += 1
            else:
                states[severity] = 1

            self.output.append("[%s] (%s) (%s) %s/%s - %s" % (
                severity,
                time_iso(alarm['_create_time']),
                alarm['node_display_name'],
                alarm['feature_display_name'],
                alarm['event_type_display_name'],
                alarm['summary'],
                ))

        count = len(self.data)
        self.summary.append("%d alarms" % count)
        self.perfdata.append("alarms=%d;;;0" % count)

        for state, value in states.items():
            self.summary.append("%d %s" % (value, state.lower()))
            self.perfdata.append("alarms.%s=%d;;;0" % (state.lower(), value))


    def build_status(self):
        states = []

        for alarm in self.data:
            if self._is_excluded(alarm):
                continue

            # HIGH == CRITICAL
            state = WARNING if alarm['severity'] in ['MEDIUM', 'LOW'] else CRITICAL
            states.append(state)

        if len(states) > 0:
            self.state = worst_state(*states)
        else:
            self.state = OK


class CapacityUsage(CheckResult):
    """
    See API Documentation: https://code.vmware.com/apis/1083/nsx-t
    https://vdc-download.vmware.com/vmwb-repository/dcr-public/787988e9-6348-4b2a-8617-e6d672c690ee/a187360c-77d5-4c0c-92a8-8e07aa161a27/api_includes/method_GetProtonCapacityUsage.html
    """

    def __init__(self, data, max_age, excludes):
        super().__init__()
        self.data = data
        self.max_age = max_age
        self.excludes = excludes
        if excludes is None:
            self.excludes = []

    def _is_excluded(self, usage):
        # to exclude via --exclude
        identifier = "%s %s" % (
            usage['severity'],
            usage['display_name'])

        for exclude in self.excludes:
            regexp = re.compile(exclude)
            if bool(regexp.search(identifier)):
                return True
        return False

    def build_output(self):
        states = {}

        for usage in self.data['capacity_usage']:
            if self._is_excluded(usage):
                continue

            severity = usage['severity']  # INFO, WARNING, CRITICAL, ERROR

            if severity in states:
                states[severity] += 1
            else:
                states[severity] = 1

            if severity == "INFO":
                state = "OK"
            elif severity == "WARNING":
                state = "WARNING"
            else:
                state = "CRITICAL"

            self.output.append("[%s] [%s] %s: %d of %d (%g%%)" % (
                state,
                usage['severity'],
                usage['display_name'],
                usage['current_usage_count'],
                usage['max_supported_count'],
                usage['current_usage_percentage'],
            ))

            label = usage['usage_type'].lower()
            self.perfdata.append("%s=%g%%;%d;%d;0;100" % (label, usage['current_usage_percentage'], usage['min_threshold_percentage'], usage['max_threshold_percentage']))
            # Maybe we need count at some point...
            # self.perfdata.append("%s_count=%d;;;0;%d" % (label, usage['current_usage_count'], usage['max_supported_count']))

        for state, value in states.items():
            self.summary.append("%d %s" % (value, state.lower()))

        if len(states) == 0:
            self.summary.append("no usages")

        self.summary.append("last update: " + time_iso(self.data['meta_info']['last_updated_timestamp']))

    def build_status(self):
        states = []

        now = datetime.datetime.now()
        last_updated = build_datetime(self.data['meta_info']['last_updated_timestamp'])

        if (now-last_updated).total_seconds() / 60 > self.max_age:
            states.append(WARNING)
            self.summary.append("last update older than %s minutes" % (self.max_age))

        for usage in self.data['capacity_usage']:
            if self._is_excluded(usage):
                continue

            severity = usage['severity']  # INFO, WARNING, CRITICAL, ERROR

            if severity == "INFO":
                state = OK
            elif severity == "WARNING":
                state = WARNING
            else:
                state = CRITICAL

            states.append(state)

        self.state = worst_state(*states)


def build_datetime(timestamp_ms):
    """
    Build a datetime from the epoch including milliseconds the API returns
    """
    return datetime.datetime.fromtimestamp(timestamp_ms / 1000)


def time_iso(timestamp_ms):
    """
    Return a simple ISO datetime string without ms
    """
    return build_datetime(timestamp_ms).strftime("%Y-%m-%d %H:%M:%S")


def worst_state(*states):
    overall = -1

    for state in states:
        if state == CRITICAL:
            overall = CRITICAL
        elif state == UNKNOWN:
            if overall != CRITICAL:
                overall = UNKNOWN
        elif state > overall:
            overall = state

    if overall < 0 or overall > 3:
        overall = UNKNOWN

    return overall


def commandline(args):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('--api', '-A', required=True,
        help='VMware NSX-T URL without any sub-path (e.g. https://vmware-nsx.local)')
    parser.add_argument('--username', '-u',
                        help='Username for Basic Auth', required=True)
    parser.add_argument('--password', '-p',
                        help='Password for Basic Auth', required=True)
    parser.add_argument('--mode', '-m', choices=['cluster-status', 'alarms', 'capacity-usage'],
                        help='Check mode to exectue. Hint: alarms will only include open alarms.', required=True)
    parser.add_argument('--exclude', nargs='*', action='extend', type=str,
                        help="Exclude alarms or usage from the check results. Can be used multiple times and supports regular expressions.")
    parser.add_argument('--max-age', '-M', type=int,
                        help='Max age in minutes for capacity usage updates. Defaults to 5', default=5, required=False)
    parser.add_argument('--insecure',
                        help='Do not verify TLS certificate', action='store_true', required=False)
    parser.add_argument('--version', '-V',
                        help='Print version', action='store_true')

    return parser.parse_args(args)


def main(args):
    fix_tls_cert_store(ssl.get_default_verify_paths().cafile)

    if args.insecure:
        urllib3.disable_warnings()

    if args.version:
        print(f"check_vmware_nsxt version {__version__}")
        return 3

    client = Client(args.api, args.username, args.password, verify=(not args.insecure), max_age=args.max_age)

    if args.mode == 'cluster-status':
        return client.get_cluster_status(args.exclude).print_and_return()
    if args.mode == 'alarms':
        return client.get_alarms(args.exclude).print_and_return()
    if args.mode == 'capacity-usage':
        return client.get_capacity_usage(args.exclude).print_and_return()

    print("[UNKNOWN] unknown mode %s" % args.mode)
    return UNKNOWN


if __package__ == '__main__' or __package__ is None: # pragma: no cover
    try:
        ARGS = commandline(sys.argv[1:])
        sys.exit(main(ARGS))
    except CriticalException as main_exc:
        print("[CRITICAL] " + str(main_exc))
        sys.exit(CRITICAL)
    except Exception: # pylint: disable=broad-except
        exception = sys.exc_info()
        print("[UNKNOWN] Unexpected Python error: %s %s" % (exception[0], exception[1]))
        sys.exit(UNKNOWN)
