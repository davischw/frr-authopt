#!/usr/bin/env python

#
# test_msdp_topo1.py
# Part of NetDEF Topology Tests
#
# Copyright (c) 2021 by
# Network Device Education Foundation, Inc. ("NetDEF")
#
# Permission to use, copy, modify, and/or distribute this software
# for any purpose with or without fee is hereby granted, provided
# that the above copyright notice and this permission notice appear
# in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND NETDEF DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL NETDEF BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY
# DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
# WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS
# ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE
# OF THIS SOFTWARE.
#

"""
test_msdp_topo1.py: Test the FRR PIM MSDP peer.
"""

import os
import sys
import json
import socket
import tempfile
from functools import partial
import pytest

# Save the Current Working Directory to find configuration files.
CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../"))

# pylint: disable=C0413
# Import topogen and topotest helpers
from lib import topotest
from lib.topogen import Topogen, TopoRouter, get_topogen
from lib.topolog import logger

# Required to instantiate the topology builder class.
from mininet.topo import Topo

pytestmark = [pytest.mark.bgpd, pytest.mark.pimd]

#
# Test global variables:
# They are used to handle communicating with external application.
#
APP_SOCK_PATH = '/tmp/topotests/apps.sock'
HELPER_APP_PATH = os.path.join(CWD, "../lib/mcast-tester.py")
app_listener = None
app_clients = {}


def listen_to_applications():
    "Start listening socket to connect with applications."
    # Remove old socket.
    try:
        os.unlink(APP_SOCK_PATH)
    except OSError:
        pass

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0)
    sock.bind(APP_SOCK_PATH)
    sock.listen(10)
    global app_listener
    app_listener = sock


def accept_host(host):
    "Accept connection from application running in hosts."
    global app_listener, app_clients
    conn = app_listener.accept()
    app_clients[host] = {
        'fd': conn[0],
        'address': conn[1]
    }


def close_applications():
    "Signal applications to stop and close all sockets."
    global app_listener, app_clients

    # Close listening socket.
    app_listener.close()

    # Remove old socket.
    try:
        os.unlink(APP_SOCK_PATH)
    except OSError:
        pass

    # Close all host connections.
    for host in ["h1", "h2"]:
        if app_clients.get(host) is None:
            continue
        app_clients[host]["fd"].close()


class MSDPTopo1(Topo):
    "Test topology builder"

    def build(self, *_args, **_opts):
        "Build function"
        tgen = get_topogen(self)

        # Create 4 routers
        for routern in range(1, 5):
            tgen.add_router("r{}".format(routern))

        switch = tgen.add_switch("s1")
        switch.add_link(tgen.gears["r1"])
        switch.add_link(tgen.gears["r2"])

        switch = tgen.add_switch("s2")
        switch.add_link(tgen.gears["r1"])
        switch.add_link(tgen.gears["r3"])

        switch = tgen.add_switch("s3")
        switch.add_link(tgen.gears["r2"])
        switch.add_link(tgen.gears["r4"])

        switch = tgen.add_switch("s4")
        #switch.add_link(tgen.gears["r3"])
        switch.add_link(tgen.gears["r4"])

        switch = tgen.add_switch("s5")
        switch.add_link(tgen.gears["r4"])

        # Create a host connected and direct at r4:
        tgen.add_host("h1", "192.168.4.100/24", "192.168.4.1")
        switch.add_link(tgen.gears["h1"])

        # Create a host connected and direct at r1:
        switch = tgen.add_switch("s6")
        tgen.add_host("h2", "192.168.10.100/24", "192.168.10.1")
        switch.add_link(tgen.gears["r1"])
        switch.add_link(tgen.gears["h2"])


def setup_module(mod):
    "Sets up the pytest environment"
    tgen = Topogen(MSDPTopo1, mod.__name__)
    tgen.start_topology()

    router_list = tgen.routers()
    for rname, router in router_list.items():
        daemon_file = "{}/{}/zebra.conf".format(CWD, rname)
        if os.path.isfile(daemon_file):
            router.load_config(TopoRouter.RD_ZEBRA, daemon_file)

        daemon_file = "{}/{}/bgpd.conf".format(CWD, rname)
        if os.path.isfile(daemon_file):
            router.load_config(TopoRouter.RD_BGP, daemon_file)

        daemon_file = "{}/{}/pimd.conf".format(CWD, rname)
        if os.path.isfile(daemon_file):
            router.load_config(TopoRouter.RD_PIM, daemon_file)

    # Initialize all routers.
    tgen.start_router()

    # Start applications socket.
    listen_to_applications()


def teardown_module(mod):
    "Teardown the pytest environment"
    tgen = get_topogen()
    close_applications()
    tgen.stop_topology()


def test_bgp_convergence():
    "Wait for BGP protocol convergence"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("waiting for protocols to converge")

    def expect_loopback_route(router, iptype, route, proto):
        "Wait until route is present on RIB for protocol."
        logger.info("waiting route {} in {}".format(route, router))
        test_func = partial(
            topotest.router_json_cmp,
            tgen.gears[router],
            "show {} route json".format(iptype),
            {route: [{"protocol": proto}]},
        )
        _, result = topotest.run_and_expect(test_func, None, count=130, wait=1)
        assertmsg = '"{}" convergence failure'.format(router)
        assert result is None, assertmsg

    # Wait for R1
    expect_loopback_route("r1", "ip", "10.254.254.2/32", "bgp")
    expect_loopback_route("r1", "ip", "10.254.254.3/32", "bgp")
    expect_loopback_route("r1", "ip", "10.254.254.4/32", "bgp")

    # Wait for R2
    expect_loopback_route("r2", "ip", "10.254.254.1/32", "bgp")
    expect_loopback_route("r2", "ip", "10.254.254.3/32", "bgp")
    expect_loopback_route("r2", "ip", "10.254.254.4/32", "bgp")

    # Wait for R3
    expect_loopback_route("r3", "ip", "10.254.254.1/32", "bgp")
    expect_loopback_route("r3", "ip", "10.254.254.2/32", "bgp")
    expect_loopback_route("r3", "ip", "10.254.254.4/32", "bgp")

    # Wait for R4
    expect_loopback_route("r4", "ip", "10.254.254.1/32", "bgp")
    expect_loopback_route("r4", "ip", "10.254.254.2/32", "bgp")
    expect_loopback_route("r4", "ip", "10.254.254.3/32", "bgp")


def test_mroute_install():
    "Test that multicast routes propagated and installed"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    tgen.gears["h1"].run("{} '{}' '{}' '{}' &".format(
        HELPER_APP_PATH, APP_SOCK_PATH, '229.1.2.3', 'h1-eth0'))
    accept_host("h1")

    tgen.gears["h2"].run("{} --send='0.7' '{}' '{}' '{}' &".format(
        HELPER_APP_PATH, APP_SOCK_PATH, '229.1.2.3', 'h2-eth0'))
    accept_host("h2")

    #
    # Test R1 mroute
    #
    expect_1 = {
        '229.1.2.3': {
            '192.168.10.100': {
                'iif': 'r1-eth2',
                'flags': 'SFT',
                'oil': {
                    'r1-eth0': {
                        'source': '192.168.10.100',
                        'group': '229.1.2.3'
                    },
                    'r1-eth1': None
                }
            }
        }
    }
    # Create a deep copy of `expect_1`.
    expect_2 = json.loads(json.dumps(expect_1))
    # The route will be either via R2 or R3.
    expect_2['229.1.2.3']['192.168.10.100']['oil']['r1-eth0'] = None
    expect_2['229.1.2.3']['192.168.10.100']['oil']['r1-eth1'] = {
        'source': '192.168.10.100',
        'group': '229.1.2.3'
    }

    def test_r1_mroute():
        "Test r1 multicast routing table function"
        out = tgen.gears['r1'].vtysh_cmd('show ip mroute json', isjson=True)
        if topotest.json_cmp(out, expect_1) is None:
            return None
        return topotest.json_cmp(out, expect_2)

    logger.info('Waiting for R1 multicast routes')
    _, val = topotest.run_and_expect(test_r1_mroute, None, count=55, wait=2)
    assert val is None, 'multicast route convergence failure'

    #
    # Test routers 2 and 3.
    #
    # NOTE: only one of the paths will get the multicast route.
    #
    expect_r2 = {
        "229.1.2.3": {
            "192.168.10.100": {
                "iif": "r2-eth0",
                "flags": "S",
                "oil": {
                    "r2-eth1": {
                        "source": "192.168.10.100",
                        "group": "229.1.2.3",
                    }
                }
            }
        }
    }
    expect_r3 = {
        "229.1.2.3": {
            "192.168.10.100": {
                "iif": "r3-eth0",
                "flags": "S",
                "oil": {
                    "r3-eth1": {
                        "source": "192.168.10.100",
                        "group": "229.1.2.3",
                    }
                }
            }
        }
    }

    def test_r2_r3_mroute():
        "Test r2/r3 multicast routing table function"
        r2_out = tgen.gears['r2'].vtysh_cmd('show ip mroute json', isjson=True)
        r3_out = tgen.gears['r3'].vtysh_cmd('show ip mroute json', isjson=True)

        if topotest.json_cmp(r2_out, expect_r2) is not None:
            return topotest.json_cmp(r3_out, expect_r3)

        return topotest.json_cmp(r2_out, expect_r2)

    logger.info('Waiting for R2 and R3 multicast routes')
    _, val = topotest.run_and_expect(test_r2_r3_mroute, None, count=55, wait=2)
    assert val is None, 'multicast route convergence failure'

    #
    # Test router 4
    #
    expect_4 = {
        "229.1.2.3": {
            "*": {
                "iif": "lo",
                "flags": "SC",
                "oil": {
                    "pimreg": {
                        "source": "*",
                        "group": "229.1.2.3",
                        "inboundInterface": "lo",
                        "outboundInterface": "pimreg"
                    },
                    "r4-eth2": {
                        "source": "*",
                        "group": "229.1.2.3",
                        "inboundInterface": "lo",
                        "outboundInterface": "r4-eth2"
                    }
                }
            },
            "192.168.10.100": {
                "iif": "r4-eth0",
                "flags": "ST",
                "oil": {
                    "r4-eth2": {
                        "source": "192.168.10.100",
                        "group": "229.1.2.3",
                        "inboundInterface": "r4-eth0",
                        "outboundInterface": "r4-eth2",
                    }
                }
            }
        }
    }

    test_func = partial(
        topotest.router_json_cmp,
        tgen.gears['r4'], "show ip mroute json", expect_4,
    )
    logger.info('Waiting for R4 multicast routes')
    _, val = topotest.run_and_expect(test_func, None, count=55, wait=2)
    assert val is None, 'multicast route convergence failure'


def test_msdp():
    """
    Test MSDP convergence.

    MSDP non meshed groups must propagate the whole SA database (not just
    their own) to all peers because not all peers talk with each other.

    This setup leads to a potential loop that can be prevented by checking
    the route's first AS in AS path: it must match the remote eBGP AS number.
    """
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1_expect = {
        "192.168.0.2": {
            "peer": "192.168.0.2",
            "local": "192.168.0.1",
            "state": "established"
        },
        "192.168.1.2": {
            "peer": "192.168.1.2",
            "local": "192.168.1.1",
            "state": "established"
        }
    }
    r1_sa_expect = {
        "229.1.2.3": {
            "192.168.10.100": {
                "source": "192.168.10.100",
                "group": "229.1.2.3",
                "rp": "-",
                "local": "yes",
                "sptSetup": "-"
            }
        }
    }
    r2_expect = {
        "192.168.0.1": {
            "peer": "192.168.0.1",
            "local": "192.168.0.2",
            "state": "established"
        },
        "192.168.2.2": {
            "peer": "192.168.2.2",
            "local": "192.168.2.1",
            "state": "established"
        }
    }
    # Only R2 or R3 will get this SA.
    r2_r3_sa_expect = {
        "229.1.2.3": {
            "192.168.10.100": {
                "source": "192.168.10.100",
                "group": "229.1.2.3",
                "rp": "192.168.1.1",
                "local": "no",
                "sptSetup": "no",
            }
        }
    }
    r3_expect = {
        "192.168.1.1": {
            "peer": "192.168.1.1",
            "local": "192.168.1.2",
            "state": "established"
        },
        #"192.169.3.2": {
        #    "peer": "192.168.3.2",
        #    "local": "192.168.3.1",
        #    "state": "established"
        #}
    }
    r4_expect = {
        "192.168.2.1": {
            "peer": "192.168.2.1",
            "local": "192.168.2.2",
            "state": "established"
        },
        #"192.168.3.1": {
        #    "peer": "192.168.3.1",
        #    "local": "192.168.3.2",
        #    "state": "established"
        #}
    }
    r4_sa_expect = {
        "229.1.2.3": {
            "192.168.10.100": {
                "source": "192.168.10.100",
                "group": "229.1.2.3",
                "rp": "192.168.1.1",
                "local": "no",
                "sptSetup": "yes"
            }
        }
    }

    for router in [('r1', r1_expect, r1_sa_expect),
                   ('r2', r2_expect, r2_r3_sa_expect),
                   ('r3', r3_expect, r2_r3_sa_expect),
                   ('r4', r4_expect, r4_sa_expect)]:
        test_func = partial(
            topotest.router_json_cmp,
            tgen.gears[router[0]], "show ip msdp peer json", router[1]
        )
        logger.info('Waiting for {} msdp peer data'.format(router[0]))
        _, val = topotest.run_and_expect(test_func, None, count=30, wait=1)
        assert val is None, 'multicast route convergence failure'

        test_func = partial(
            topotest.router_json_cmp,
            tgen.gears[router[0]], "show ip msdp sa json", router[2]
        )
        logger.info('Waiting for {} msdp SA data'.format(router[0]))
        _, val = topotest.run_and_expect(test_func, None, count=30, wait=1)
        assert val is None, 'multicast route convergence failure'


def test_memory_leak():
    "Run the memory leak test and report results."
    tgen = get_topogen()
    if not tgen.is_memleak_enabled():
        pytest.skip("Memory leak test/report is disabled")

    tgen.report_memory_leaks()


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args))
