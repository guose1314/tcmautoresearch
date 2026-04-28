"""Bounded context packages.

Each subpackage under ``src.contexts`` is an independent bounded context
that owns its domain model, services and storage adapters. They sit
alongside ``src.research`` (the research process orchestrator) and may
depend on storage / infra layers but **not** on each other.
"""
