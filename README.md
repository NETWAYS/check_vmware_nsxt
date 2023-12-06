# check_vmware_nsxt

Icinga check plugin for the VMware NSX-T REST API.

Supported Modes:

* cluster-status - retrieves the overall NSX-T cluster status from the API
* alarms - Retrieve and display open alarms from the API
* capacity-usage - Retrieves and checks capacity indicators from the API

## Installation

Python 3 is required, and you need the Python [requests](https://pypi.org/project/requests/) module.

Please prefer installation via system packages like `python3-requests`.

Alternatively you can install with pip:

    pip3 install -r requirements.txt

## Usage

```
check_vmware_nsxt.py --help

optional arguments:
  -h, --help            show this help message and exit
  --api API, -A API     VMware NSX-T URL without any sub-path (e.g. https://vmware-nsx.local)
  --username USERNAME, -u USERNAME
                        Username for Basic Auth (CHECK_VMWARE_NSXT_API_USER)
  --password PASSWORD, -p PASSWORD
                        Password for Basic Auth (CHECK_VMWARE_NSXT_API_PASSWORD)
  --mode MODE, -m MODE  Check mode
  --exclude [EXCLUDE ...]
                        Exclude alarms or usage from the check results.
                        Can be used multiple times and supports regular expressions.
  --max-age MAX_AGE, -M MAX_AGE
                        Max age in minutes for capacity usage updates. Defaults to 5
  --version, -V         Print version
  --insecure            Do not verify TLS certificate. Be careful with this option, please
```

The `--exclude` parameter will match against alarms and capacity-usage. It uses the following string representation (whitespaces included) to match against:

* alarms: `severity` `node_display_name` `feature_display_name` `event_type_display_name`
* capacity-usage: `severity` `display_name`

Various flags can be set with environment variables, refer to the help to see which flags.

## Examples

Mode: cluster-status

```
check_vmware_nsxt.py --api 'https://vmware-nsx.local' -u icinga -p password --mode cluster-status

[OK] control_cluster_status=STABLE - mgmt_cluster_status=STABLE - control_cluster_status=STABLE - nodes_online=3

[OK] DATASTORE: STABLE - 3 members
[OK] CLUSTER_BOOT_MANAGER: STABLE - 3 members
[OK] CONTROLLER: STABLE - 3 members
[OK] MANAGER: STABLE - 3 members
[OK] POLICY: STABLE - 3 members
[OK] HTTPS: STABLE - 3 members
[OK] ASYNC_REPLICATOR: STABLE - 3 members
[OK] MONITORING: STABLE - 3 members
[OK] IDPS_REPORTING: STABLE - 3 members
[OK] CORFU_NONCONFIG: STABLE - 3 members
| nodes_online=3;;;0
```

Mode: alarms

```
check_vmware_nsxt.py --api 'https://vmware-nsx.local' -u icinga -p password --mode alarms

[WARNING] 1 alarms - 1 medium

[MEDIUM] (2021-04-26 17:25:18) (node1) Intelligence Health/Storage Latency High - Intelligence node storage latency is high.
| alarms=1;;;0 alarms.medium=1;;;0
```

```
check_vmware_nsxt.py --api 'https://vmware-nsx.local' -u icinga -p password --mode alarms --exclude "LOW"
# Hint: Excluded alerts will still be counted, but are not factored into the exit code

[OK] 1 alarms
| alarms=1;;;0
```

Mode: capacity-usage

```
check_vmware_nsxt.py --api 'https://vmware-nsx.local' -u icinga -p password --mode capacity-usage

[OK] 28 info - no usages - last update: 2021-04-29 19:06:12

[OK] [INFO] System-wide NAT rules: 0 of 25000 (0%)
[OK] [INFO] Network Introspection Rules: 1 of 10000 (0.01%)
[OK] [INFO] System-wide Endpoint Protection Enabled Hosts: 0 of 256 (0%)
...
| number_of_nat_rules=0%;70;100;0;100
number_of_si_rules=0.01%;70;100;0;100
number_of_gi_protected_hosts=0%;70;100;0;100
...
```

## API Documentation

[VMware-NSX-T-Data-Center docs](https://docs.vmware.com/en/VMware-NSX-T-Data-Center)

General API Documentation: [code.vmware.com](https://code.vmware.com/apis/1083/nsx-t)

Endpoints the check uses:
* [/api/v1/cluster-status](https://vdc-download.vmware.com/vmwb-repository/dcr-public/787988e9-6348-4b2a-8617-e6d672c690ee/a187360c-77d5-4c0c-92a8-8e07aa161a27/api_includes/method_ReadClusterStatus.html)
* [/api/v1/alarms](https://vdc-download.vmware.com/vmwb-repository/dcr-public/787988e9-6348-4b2a-8617-e6d672c690ee/a187360c-77d5-4c0c-92a8-8e07aa161a27/api_includes/method_GetAlarms.html)
* [/api/v1/capacity/usage](https://vdc-download.vmware.com/vmwb-repository/dcr-public/787988e9-6348-4b2a-8617-e6d672c690ee/a187360c-77d5-4c0c-92a8-8e07aa161a27/api_includes/method_GetProtonCapacityUsage.html)

## License

VMware NSX® is a trademark of VMware, Inc.

Copyright (C) 2021 [NETWAYS GmbH](mailto:info@netways.de)

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
