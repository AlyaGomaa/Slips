# SPDX-FileCopyrightText: 2021 Sebastian Garcia <sebastian.garcia@agents.fel.cvut.cz>
# SPDX-License-Identifier: GPL-2.0-only
from typing import Any

from slips_files.core.database.database_manager import DBManager

DHCPV6_PORTS = {"546", "547"}


def should_ignore_different_localnet_for_official_dns_server(
    db: DBManager,
    flow: Any,
    what_to_check: str,
) -> bool:
    """
    Check whether different-localnet evidence should be skipped.

    Parameters:
    db: Database manager used to check known official DNS servers.
    flow: Flow-like object being analyzed.
    what_to_check: IP direction being evaluated, either srcip or dstip.

    Return:
    bool: True when the checked IP is a detected DNS server using port 53.
    """
    if what_to_check == "dstip":
        dns_server_ip = getattr(flow, "daddr", "")
        dns_server_port = getattr(flow, "dport", "")
    elif what_to_check == "srcip":
        dns_server_ip = getattr(flow, "saddr", "")
        dns_server_port = getattr(flow, "sport", "")
    else:
        return False

    if str(dns_server_port) != "53" or not dns_server_ip:
        return False

    return db.is_official_dns_server(dns_server_ip)


def should_ignore_dns_or_dhcpv6_flow(
    db: DBManager,
    flow: Any,
) -> bool:
    """
    Check whether private-IP connection evidence should be skipped.

    Parameters:
    db: Database manager used to check known official DNS servers.
    flow: Flow-like object being analyzed.

    Return:
    bool: True when the flow is a DNS query to port 53, a DNS reply from a
    detected DNS server, or DHCPv6 service traffic.
    """
    if getattr(flow, "proto", "").lower() != "udp":
        return False

    daddr = getattr(flow, "daddr", "")
    saddr = getattr(flow, "saddr", "")
    dport = str(getattr(flow, "dport", ""))
    sport = str(getattr(flow, "sport", ""))

    if dport == "53" and daddr:
        return True

    if sport == "53" and saddr and db.is_official_dns_server(saddr):
        return True

    if sport in DHCPV6_PORTS or dport in DHCPV6_PORTS:
        return True

    return False
