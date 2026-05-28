"""Testes do `imports.baixar_planilha_familiar`.

Cobre:
  - `normalizar_url`: aceita várias formas e devolve sempre o
    endpoint `.../export?format=xlsx`.
  - `baixar`: mocka `urlopen` pra evitar dependência de rede; valida
    sanity check do magic number XLSX e gravação em disco.
  - `salvar_url` / `url_salva`: round-trip do cache local.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from imports import baixar_planilha_familiar as mod


def test_normalizar_url_edit_link() -> None:
    url = "https://docs.google.com/spreadsheets/d/AbC123_xy-z/edit#gid=42"
    assert (
        mod.normalizar_url(url)
        == "https://docs.google.com/spreadsheets/d/AbC123_xy-z/export?format=xlsx"
    )


def test_normalizar_url_ja_export() -> None:
    url = (
        "https://docs.google.com/spreadsheets/d/zzz/export?format=xlsx&gid=0"
    )
    assert mod.normalizar_url(url) == url


def test_normalizar_url_publicada() -> None:
    """URL de planilha publicada (`/d/e/<ID>/pubhtml`) também deve ser
    aceita — o regex captura o ID em ambos os casos."""
    url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vXY/pubhtml"
    saida = mod.normalizar_url(url)
    assert "/export?format=xlsx" in saida
    assert "2PACX-1vXY" in saida


def test_normalizar_url_invalida() -> None:
    with pytest.raises(ValueError, match="extrair o ID"):
        mod.normalizar_url("https://example.com/foo/bar")


def test_normalizar_url_vazia() -> None:
    with pytest.raises(ValueError, match="URL vazia"):
        mod.normalizar_url("")


def test_salvar_e_ler_url(tmp_path, monkeypatch) -> None:
    """Round-trip do cache de URL em disco."""
    cache = tmp_path / "planilha_url.txt"
    monkeypatch.setattr(mod, "DADOS_DIR", tmp_path)
    monkeypatch.setattr(mod, "ARQUIVO_URL_CACHE", cache)
    monkeypatch.delenv(mod.ENV_URL, raising=False)

    assert mod.url_salva() == ""

    mod.salvar_url("  https://docs.google.com/spreadsheets/d/XYZ/edit  ")
    assert cache.exists()
    assert mod.url_salva() == "https://docs.google.com/spreadsheets/d/XYZ/edit"


def test_url_salva_usa_env_quando_sem_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "DADOS_DIR", tmp_path)
    monkeypatch.setattr(mod, "ARQUIVO_URL_CACHE", tmp_path / "no.txt")
    monkeypatch.setenv(mod.ENV_URL, "https://docs.google.com/spreadsheets/d/ENV/edit")
    assert mod.url_salva() == "https://docs.google.com/spreadsheets/d/ENV/edit"


class _RespostaFake:
    def __init__(self, conteudo: bytes, status: int = 200) -> None:
        self._stream = io.BytesIO(conteudo)
        self.status = status

    def read(self) -> bytes:
        return self._stream.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self._stream.close()


def test_baixar_xlsx_ok(tmp_path, monkeypatch) -> None:
    """Mocka `urlopen` devolvendo bytes começando com magic XLSX e
    confirma que o arquivo é gravado no destino indicado."""
    destino = tmp_path / "out.xlsx"
    conteudo_fake = b"PK\x03\x04" + b"resto fake do zip\x00\x01\x02"

    def _fake_urlopen(req, timeout=None):  # noqa: ARG001
        return _RespostaFake(conteudo_fake)

    monkeypatch.setattr(mod, "urlopen", _fake_urlopen)
    monkeypatch.setattr(mod, "ARQUIVO_URL_CACHE", tmp_path / "no.txt")
    monkeypatch.delenv(mod.ENV_URL, raising=False)

    caminho = mod.baixar(
        "https://docs.google.com/spreadsheets/d/ABC/edit",
        destino=destino,
    )

    assert caminho == destino
    assert destino.read_bytes() == conteudo_fake


def test_baixar_nao_xlsx_levanta(tmp_path, monkeypatch) -> None:
    """Se a URL devolver algo que não é XLSX (ex.: HTML de 'login
    required'), `baixar` deve levantar erro claro pro usuário."""
    destino = tmp_path / "out.xlsx"
    conteudo_html = b"<!DOCTYPE html><html>...login required..."

    def _fake_urlopen(req, timeout=None):  # noqa: ARG001
        return _RespostaFake(conteudo_html)

    monkeypatch.setattr(mod, "urlopen", _fake_urlopen)
    monkeypatch.setattr(mod, "ARQUIVO_URL_CACHE", tmp_path / "no.txt")
    monkeypatch.delenv(mod.ENV_URL, raising=False)

    with pytest.raises(RuntimeError, match="XLSX"):
        mod.baixar(
            "https://docs.google.com/spreadsheets/d/ABC/edit",
            destino=destino,
        )

    assert not destino.exists()


def test_baixar_sem_url(tmp_path, monkeypatch) -> None:
    """Sem URL nem cache nem env → erro claro."""
    monkeypatch.setattr(mod, "ARQUIVO_URL_CACHE", tmp_path / "no.txt")
    monkeypatch.delenv(mod.ENV_URL, raising=False)

    with pytest.raises(RuntimeError, match="URL não informada"):
        mod.baixar(None, destino=tmp_path / "x.xlsx")


def test_baixar_usa_cache_quando_url_omitida(tmp_path, monkeypatch) -> None:
    """Quando `url` é omitida, lê do cache em disco."""
    cache = tmp_path / "planilha_url.txt"
    cache.write_text(
        "https://docs.google.com/spreadsheets/d/CACHE/edit", encoding="utf-8"
    )
    monkeypatch.setattr(mod, "DADOS_DIR", tmp_path)
    monkeypatch.setattr(mod, "ARQUIVO_URL_CACHE", cache)
    monkeypatch.delenv(mod.ENV_URL, raising=False)

    conteudo_fake = b"PK\x03\x04xlsx"
    urls_capturadas: list[str] = []

    def _fake_urlopen(req, timeout=None):  # noqa: ARG001
        urls_capturadas.append(req.full_url)
        return _RespostaFake(conteudo_fake)

    monkeypatch.setattr(mod, "urlopen", _fake_urlopen)

    destino = tmp_path / "x.xlsx"
    mod.baixar(destino=destino)

    assert urls_capturadas == [
        "https://docs.google.com/spreadsheets/d/CACHE/export?format=xlsx"
    ]
    assert destino.read_bytes() == conteudo_fake


def test_main_salva_url_e_baixa(tmp_path, monkeypatch, capsys) -> None:
    cache = tmp_path / "planilha_url.txt"
    monkeypatch.setattr(mod, "DADOS_DIR", tmp_path)
    monkeypatch.setattr(mod, "ARQUIVO_URL_CACHE", cache)
    monkeypatch.setattr(mod, "ARQUIVO_BAIXADO", tmp_path / "saida.xlsx")
    monkeypatch.delenv(mod.ENV_URL, raising=False)

    monkeypatch.setattr(
        mod, "urlopen", lambda req, timeout=None: _RespostaFake(b"PK\x03\x04ok")
    )

    rc = mod.main(["https://docs.google.com/spreadsheets/d/MAIN/edit"])
    out = capsys.readouterr().out

    assert rc == 0
    assert cache.read_text(encoding="utf-8").strip().startswith(
        "https://docs.google.com/spreadsheets/d/MAIN/edit"
    )
    assert (tmp_path / "saida.xlsx").read_bytes() == b"PK\x03\x04ok"
    assert "Planilha baixada em:" in out


def test_main_falha_sem_url(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(mod, "ARQUIVO_URL_CACHE", tmp_path / "no.txt")
    monkeypatch.setattr(mod, "ARQUIVO_BAIXADO", tmp_path / "x.xlsx")
    monkeypatch.delenv(mod.ENV_URL, raising=False)

    rc = mod.main([])
    err = capsys.readouterr().err
    assert rc == 1
    assert "URL" in err


def _tmp_path_existence_check(p: Path) -> bool:
    """Auxiliar usado em alguns ambientes onde `tmp_path` pode não
    persistir corretamente entre chamadas."""
    return p.exists()
