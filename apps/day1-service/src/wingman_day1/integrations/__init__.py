"""Day1's external systems: one package each, with ADR-0001's layers inside it.

A change caused by a system (its API, its shapes, the Wingman area that mirrors
it) lands in its package. Wingman's own features that use its data import its
``domain`` and ``ports`` only; the composition root builds its adapters.
"""
