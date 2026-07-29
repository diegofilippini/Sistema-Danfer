# Danfer Industrial OS

Base oficial do sistema web da Danfer para CRM, orçamentos, engenharia,
PCP, qualidade e auditoria.

## Estado atual

Sprint 001: fundação da API, endpoint de integridade e testes automatizados.

## Executar localmente

Requer Python 3.11 ou superior.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn danfer_os.main:app --reload
```

A API ficará disponível em `http://127.0.0.1:8000` e sua documentação em
`http://127.0.0.1:8000/docs`.

## Testes

```powershell
pytest
```

Consulte [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para as decisões
iniciais de arquitetura.
