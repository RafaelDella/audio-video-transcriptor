#!/usr/bin/env python3
"""Compatibilidade com a versao antiga. Prefira o comando `transcreve`."""

from __future__ import annotations

from transcreve.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
