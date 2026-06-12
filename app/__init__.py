"""Lexio application package.

Phase 2 of the refactor (see REFACTOR_PLAN.md) is extracting the 4,000-line
main.py into this package one cohesive module at a time. main.py re-imports
the moved names so `main:app` and the test surface stay identical while the
implementation physically relocates here.
"""
