"""Permite `python -m tokenmeter <subcomando>`.

O pacote aqui é uma cópia vendorizada dentro do projeto hospedeiro, não uma
instalação via pip — logo não existe o executável `tokenmeter` no PATH. Sem este
arquivo, rodar o painel ou o doctor exigiria um `python -c` com import manual.
"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
