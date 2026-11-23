"""segments-manager: the platform's ledger of VLAN segments (ADR-0039).

Read only. Its links, port, HTTP adapter, cache, fake and composition. A
cluster's network check (the EPG) reads it through ``ports.SegmentLedger``;
the check itself is Wingman's (``wingman_day1.domain.network``).
"""
