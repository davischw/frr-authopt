#!/usr/bin/python

import os
import sys
import time
import pytest
import json

CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../"))
sys.path.append(os.path.join(CWD, "../lib/"))

from mininet.topo import Topo
from lib.topogen import Topogen, get_topogen

from lib.common_config import (
    start_topology,
    write_test_header,
    write_test_footer,
    reset_config_on_routers,
    stop_router,
    start_router,
    verify_rib,
    create_static_routes,
    step,
    start_router_daemons,
    shutdown_bringup_interface,
    topo_daemons,
    create_prefix_lists,
    create_interfaces_cfg,
    run_frr_cmd,
)
from lib.topolog import logger
from lib.topojson import build_topo_from_json, build_config_from_json
from lib.ospf import (
    verify_ospf_neighbor,
    verify_ospf6_neighbor,
    create_router_ospf,
    create_router_ospf6,
    verify_ospf_summary,
    redistribute_ospf,
    verify_ospf_database,
)

pytestmark = [pytest.mark.ospfd, pytest.mark.staticd]


# Global variables
topo = None

# Reading the data from JSON File for topology creation
jsonFile = "{}/test_ospf_dual_stack.json".format(CWD)
try:
    with open(jsonFile, "r") as topoJson:
        topo = json.load(topoJson)
except IOError:
    assert False, "Could not read file {}".format(jsonFile)


class CreateTopo(Topo):
    """Test topology builder."""

    def build(self, *_args, **_opts):
        """Build function."""
        tgen = get_topogen(self)

        # Building topology from json file
        build_topo_from_json(tgen, topo)


def setup_module(mod):
    """Sets up the pytest environment."""
    global topo
    testsuite_run_time = time.asctime(time.localtime(time.time()))
    logger.info("Testsuite start time: {}".format(testsuite_run_time))
    logger.info("=" * 40)

    logger.info("Running setup_module to create topology")

    # This function initiates the topology build with Topogen...
    tgen = Topogen(CreateTopo, mod.__name__)
    # ... and here it calls Mininet initialization functions.

    # get list of daemons needs to be started for this suite.
    daemons = topo_daemons(tgen, topo)

    # Starting topology, create tmp files which are loaded to routers
    #  to start daemons and then start routers
    start_topology(tgen, daemons)

    # Creating configuration from JSON
    build_config_from_json(tgen, topo)

    # Don't run this test if we have any failure.
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    # Api call verify whether OSPF converged
    ospf_covergence_ipv4 = verify_ospf_neighbor(tgen, topo)
    assert ospf_covergence_ipv4 is True, "setup_module :Failed \n Error:" " {}".format(
        ospf_covergence_ipv4
    )

    # Api call verify whether OSPF6 converged
    ospf_covergence_ipv6 = verify_ospf6_neighbor(tgen, topo)
    assert ospf_covergence_ipv6 is True, "setup_module :Failed \n Error:" " {}".format(
        ospf_covergence_ipv6
    )
    logger.info("Running setup_module() done")


def teardown_module(mod):
    """
    Teardown the pytest environment.

    * `mod`: module name
    """

    logger.info("Running teardown_module to delete topology")
    tgen = get_topogen()
    # Stop topology and remove tmp files
    tgen.stop_topology()
    logger.info(
        "Testsuite end time: {}".format(time.asctime(time.localtime(time.time())))
    )
    logger.info("=" * 40)


#
# ##################################
# Test cases start here.
# ##################################
#
#
def test_ospf_dual_stack(request):
    """OSPF test dual stack."""

    tc_name = request.node.name
    write_test_header(tc_name)

    # Don't run this test if we have any failure.
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    global topo

    step("Bring up the base configuration as per the JSON topology")
    reset_config_on_routers(tgen)
    write_test_footer(tc_name)


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args))
