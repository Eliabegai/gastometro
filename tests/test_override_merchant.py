"""Override de categoria por comerciante (cobre variantes de grafia)."""

from __future__ import annotations

from db.engine import get_session
from db.repository import (
    _cache_overrides,
    _categorizar_para_id,
    chave_override_merchant,
    listar_overrides_dict,
    salvar_override,
    salvar_override_merchant,
)


def _categoria(descricao: str) -> str:
    with get_session() as session:
        overrides = _cache_overrides(session)
        return _categorizar_para_id(session, descricao, overrides)[1]


def test_chave_override_merchant_agrupa_variantes() -> None:
    a = chave_override_merchant("PADARIA ZE 123")
    b = chave_override_merchant("Padaria Ze 456")
    assert a.startswith("m:") and a == b


def test_chave_vazia_sem_descricao() -> None:
    assert chave_override_merchant("") == ""


def test_override_merchant_vale_para_todas_as_variantes(banco_temporario) -> None:
    salvar_override_merchant("PADARIA ZE 123", "Mercado")
    assert _categoria("PADARIA ZE 123") == "Mercado"
    assert _categoria("Padaria Ze 456") == "Mercado"
    assert any(k.startswith("m:") for k in listar_overrides_dict())


def test_override_exato_tem_precedencia_sobre_merchant(banco_temporario) -> None:
    salvar_override_merchant("PADARIA ZE 123", "Mercado")
    salvar_override("Padaria Ze 456", "Lazer")
    assert _categoria("Padaria Ze 456") == "Lazer"
    assert _categoria("PADARIA ZE 123") == "Mercado"


def test_salvar_merchant_duas_vezes_atualiza(banco_temporario) -> None:
    salvar_override_merchant("PADARIA ZE 123", "Mercado")
    salvar_override_merchant("PADARIA ZE 999", "Lazer")
    assert _categoria("PADARIA ZE 123") == "Lazer"
    assert len([k for k in listar_overrides_dict() if k.startswith("m:")]) == 1
