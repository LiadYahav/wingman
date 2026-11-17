"""segments-manager: the platform's ledger of VLAN segments, and the Segments area (ADR-0047).

Read only. Its domain, port, use case, HTTP adapter, cache and fake, router and
composition. A cluster's network check (the EPG, ADR-0039) reads it through
``ports.SegmentLedger``; the check itself is Wingman's (``wingman_day1.domain.network``).
"""
