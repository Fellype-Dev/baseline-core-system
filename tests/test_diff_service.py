"""Testes do leitor de diff (quais linhas do arquivo novo mudaram)."""

from app.services.diff_service import linhas_alteradas


def test_linha_adicionada_e_registrada():
    diff = (
        "@@ -8,2 +8,2 @@\n"
        "     def calcular(self, x):\n"
        "-        return x + self.base\n"
        "+        return x + self.base + 1\n"
    )
    assert linhas_alteradas(diff) == {9}


def test_linha_removida_nao_conta_nem_avanca():
    diff = (
        "@@ -1,3 +1,2 @@\n"
        " linha_a\n"
        "-linha_removida\n"
        " linha_c\n"
    )
    # Nada foi adicionado ao arquivo novo -> conjunto vazio.
    assert linhas_alteradas(diff) == set()


def test_adicoes_consecutivas():
    diff = (
        "@@ -5,1 +5,3 @@\n"
        " contexto\n"
        "+nova1\n"
        "+nova2\n"
    )
    # contexto=5, nova1=6, nova2=7
    assert linhas_alteradas(diff) == {6, 7}


def test_multiplos_hunks_no_mesmo_diff():
    diff = (
        "@@ -1,1 +1,2 @@\n"
        " a\n"
        "+b\n"
        "@@ -10,1 +11,2 @@\n"
        " j\n"
        "+k\n"
    )
    assert linhas_alteradas(diff) == {2, 12}
