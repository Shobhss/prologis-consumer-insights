"""Prologis customer-intelligence pipeline.

fetch -> normalize -> prefilter -> extract -> implicate -> report

Each stage reads and writes the SQLite store in data/pipeline.sqlite so stages
can be re-run independently. See README.md for usage and HANDOFF.md for notes.
"""
