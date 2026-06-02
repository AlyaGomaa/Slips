# SPDX-FileCopyrightText: 2021 Sebastian Garcia <sebastian.garcia@agents.fel.cvut.cz>
# SPDX-License-Identifier: GPL-2.0-only
from abc import ABC, abstractmethod

from modules.flow_alerts.set_evidence import SetEvidenceHelper
from slips_files.core.database.database_manager import DBManager


class IFlowalertsAnalyzer(ABC):
    """
    keep in mind that every class that implements this interface MUST be
    registered in flow_alerts.py
    must by started, controlled, and terminated by it. msgs from the
    appropriate channels should be passed to that class using flow_alerts too.
    """

    def __init__(self, db: DBManager, flowalerts=None, **kwargs):
        self.db = db
        self.flowalerts = flowalerts
        self.whitelist = self.flowalerts.whitelist
        self.set_evidence = SetEvidenceHelper(self.db)
        self.init(**kwargs)

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    def shutdown_gracefully(self):
        """Exits gracefully"""
        pass

    def read_configuration(self):
        """Reads configuration"""

    def should_ignore_different_localnet_for_official_dns_server(
        self, flow, what_to_check: str
    ) -> bool:
        """
        Check whether different-localnet evidence should be skipped.

        Parameters:
        flow: Flow-like object being analyzed.
        what_to_check: IP direction being evaluated, either srcip or dstip.

        Return:
        bool: True when the checked IP is a detected DNS server using
        port 53.
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

        return self.db.is_official_dns_server(dns_server_ip)

    def should_ignore_conn_to_private_ip_for_official_dns_server(
        self, flow
    ) -> bool:
        """
        Check whether private-IP connection evidence should be skipped.

        Parameters:
        flow: Flow-like object being analyzed.

        Return:
        bool: True when the flow is a DNS query to port 53, a DNS reply
        from a detected DNS server, or DHCPv6 service traffic.
        """
        if getattr(flow, "proto", "").lower() != "udp":
            return False

        daddr = getattr(flow, "daddr", "")
        saddr = getattr(flow, "saddr", "")
        dport = str(getattr(flow, "dport", ""))
        sport = str(getattr(flow, "sport", ""))

        if dport == "53" and daddr:
            return True

        if sport == "53" and saddr and self.db.is_official_dns_server(saddr):
            return True

        if {sport, dport}.intersection({"546", "547"}):
            return True

        return False

    @abstractmethod
    def init(self):
        """
        the goal of this is to have one common __init__() above for all
        flow_alerts helpers, which is the one in this file, and a different
        init() per helper
        this init will have access to all keyword args passes when
        initializing the module
        """

    @abstractmethod
    def analyze(self, msg: dict) -> bool:
        """
        Analyzes a certain flow type and runs all supported detections
        returns True if there was a detection
        """
