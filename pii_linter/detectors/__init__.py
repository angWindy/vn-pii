"""Detector plugins for PII.

Each module exposes detectors that take a (column_hints, value) pair and
return a list of ``Finding`` dataclasses. The orchestrator in
:mod:`pii_linter.cli` is responsible for dispatching.

Naming convention: ``detect_<entity>`` returns one or more ``Finding``;
lower-level ``match`` helpers return ``Match`` objects that get coalesced.
"""