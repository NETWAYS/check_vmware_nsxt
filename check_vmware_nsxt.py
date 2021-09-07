#!/usr/bin/env python
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
import requests
import datetime
from requests.auth import HTTPBasicAuth
from urllib.parse import urljoin


VERSION = '0.1.0'

OK       = 0
WARNING  = 1
CRITICAL = 2
UNKNOWN  = 3

STATES = {
    OK: "OK",
    WARNING: "WARNING",
    CRITICAL: "CRITICAL",
    UNKNOWN: "UNKNOWN",
}


def fix_tls_cert_store():
    """
    Ensure we are using the system certstore by default

    See https://github.com/psf/requests/issues/2966
    Inspired by https://github.com/psf/requests/issues/2966#issuecomment-614323746
    """
    import ssl

    try:
        system_ca_store = ssl.get_default_verify_paths().cafile
        if os.stat(system_ca_store).st_size > 0:
            requests.utils.DEFAULT_CA_BUNDLE_PATH = system_ca_store
            requests.adapters.DEFAULT_CA_BUNDLE_PATH = system_ca_store
    except:
        pass


class CriticalException(Exception):
    """
    Provide an exception that will cause the check to exit critically with an error
    """

    pass


class Client:
    """
    Simple API client for VMware NSX-T
    """

    API_PREFIX = '/api/v1/'

    def __init__(self, api, username, password, logger=None, verify=True):
        # TODO: parse and validate url?

        self.api = api
        self.username = username
        self.password = password
        self.verify = verify

        if logger is None:
            logger = logging.getLogger()

        self.logger = logger


    def request(self, url, method='GET', **kwargs):
        """
        Basic JSON request handling

        Handles authentication and returns the JSON result when successful
        """

        base_url = urljoin(self.api, self.API_PREFIX)
        request_url = urljoin(base_url, url)

        self.logger.debug("starting API %s request from: %s", method, url)

        try:
            response = requests.request(method, request_url, auth=HTTPBasicAuth(self.username, self.password), verify=self.verify)
        except requests.exceptions.RequestException as e:
            raise CriticalException(e)

        if response.status_code != 200:
            raise CriticalException('Request to %s was not successful: %s' % (request_url, response.status_code))

        try:
            return response.json()
        except Exception as e:
            raise CriticalException('Could not decode API JSON: ' + str(e))


    def get_cluster_status(self):
        """
        GET and build ClusterStatus
        """
        return ClusterStatus(self.request('cluster/status'))


    def get_alarms(self):
        """
        GET and build Alarms
        """
        status = "OPEN"
        #status = "RESOLVED" # for testing
        result = self.request('alarms?page_size=100&status=%s&sort_ascending=false' % status)
        return Alarms(result['results'])


    def get_capacity_usage(self):
        """
        GET and build CapacityUsage
        """
        return CapacityUsage(self.request('capacity/usage'))


class CheckResult:
    def __init__(self):
        self.state = -1
        self.summary = []
        self.output = []
        self.perfdata = []

    def build_output(self):
        raise NotImplemented("build_output not implemented in %s" % type(self))

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
        raise NotImplemented("build_status not implemented in %s" % type(self))

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

    def __init__(self, data):
        super().__init__()
        self.data = data

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

    def __init__(self, data):
        super().__init__()
        self.data = data

    def build_output(self):
        states = {}

        for alarm in self.data:
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

        for state in states:
            self.summary.append("%d %s" % (states[state], state.lower()))


    def build_status(self):
        states = []

        for alarm in self.data:
            state = WARNING if alarm['severity'] in ['MEDIUM', 'LOW'] else CRITICAL # CRITICAL, HIGH
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

    def __init__(self, data):
        super().__init__()
        self.data = data

    def build_output(self):
        states = {}

        for usage in self.data['capacity_usage']:
            severity = usage['severity'] # INFO, WARNING, CRITICAL, ERROR

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
            #self.perfdata.append("%s_count=%d;;;0;%d" % (label, usage['current_usage_count'], usage['max_supported_count']))

        for state in states:
            self.summary.append("%d %s" % (states[state], state.lower()))

        if len(states) == 0:
            self.summary.append("no usages")

        self.summary.append("last update: " + time_iso(self.data['meta_info']['last_updated_timestamp']))

    def build_status(self):
        states = []

        now = datetime.datetime.now()
        last_updated = build_datetime(self.data['meta_info']['last_updated_timestamp'])

        if (now-last_updated).total_seconds() / 60 > 5:
            states.append(WARNING)
            self.summary.append("last update older than 5 minutes")

        for usage in self.data['capacity_usage']:
            severity = usage['severity'] # INFO, WARNING, CRITICAL, ERROR

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


def parse_args():
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)

    args.add_argument('--api', '-A', required=True,
        help='VMware NSX-T URL without any sub-path (e.g. https://vmware-nsx.local)')

    args.add_argument('--username', '-u', help='Username for Basic Auth', required=True)
    args.add_argument('--password', '-p', help='Password for Basic Auth', required=True)

    args.add_argument('--mode', '-m', help='Check mode', required=True)

    args.add_argument('--version', '-V', help='Print version', action='store_true')

    args.add_argument('--insecure', help='Do not verify TLS certificate. Be careful with this option, please', action='store_true', required=False)

    return args.parse_args()


def main():
    fix_tls_cert_store()

    args = parse_args()
    if args.insecure:
        import urllib3
        urllib3.disable_warnings()

    if args.version:
        print("check_vmware_nsxt version %s" % VERSION)
        return 0

    client = Client(args.api, args.username, args.password, verify=(not args.insecure))

    if args.mode == 'cluster-status':
        return client.get_cluster_status().print_and_return()
    elif args.mode == 'alarms':
        return client.get_alarms().print_and_return()
    elif args.mode == 'capacity-usage':
        return client.get_capacity_usage().print_and_return()
    else:
        print("[UNKNOWN] unknown mode %s" % args.mode)
        return UNKNOWN


if __package__ == '__main__' or __package__ is None:
    try:
        sys.exit(main())
    except CriticalException as e:
        print("[CRITICAL] " + str(e))
        sys.exit(CRITICAL)
    except Exception:
        exception = sys.exc_info()
        print("[UNKNOWN] Unexpected Python error: %s %s" % (exception[0], exception[1]))

        try:
            import traceback
            traceback.print_tb(exception[2])
        except:
            pass

        sys.exit(UNKNOWN)
