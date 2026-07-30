# Danfer Industrial OS

API central dos módulos industriais da Danfer.

## Sprint 054 — Importador Inteligente

O módulo `/api/v1/imports` recebe CSV, XLSX e XLS em Base64, identifica abas e
cabeçalhos, gera uma prévia, mapeia colunas para os campos do sistema, aplica
valores fixos e valida cada linha. Mapeamentos podem ser salvos por cliente e
cada conclusão entra no histórico de importações.

## Sprint 055 — Biblioteca Técnica

O módulo permite cadastrar, consultar, pesquisar, filtrar, revisar e remover
documentos técnicos. Os endpoints ficam em `/api/v1/technical-library` e a
documentação interativa em `/docs`.

Categorias disponíveis: `desenho`, `manual`, `procedimento`, `especificacao`,
`norma` e `outro`.

## Sprint 056 — Estrutura de Produto (BOM)

O módulo `/api/v1/boms` mantém estruturas de produto versionadas, com
componentes, quantidades, unidades, perdas previstas, status e explosão
multinível. Referências a peças inexistentes, componentes duplicados e ciclos
são rejeitados.

## Sprint 057 — PCP Inteligente

O módulo `/api/v1/pcp` gera ordens de produção a partir das estruturas BOM,
calcula as necessidades multinível, agrupa demandas por material e espessura,
ordena o trabalho por prazo/prioridade e controla o fluxo Kanban das ordens.

## Sprint 058 — Integrações

O módulo `/api/v1/integrations` recebe pedidos externos por JSON ou XML,
impede reimportações, confere os códigos na Biblioteca Técnica e registra
advertências. Uma fila de eventos permite confirmar ou repetir a sincronização
com o ERP sem acoplá-lo ao restante da aplicação.

## Sprint 059 — Dashboard Industrial

O endpoint `/api/v1/dashboard/industrial` consolida peças técnicas, estruturas
ativas, ordens por situação, atrasos, próximas ordens, demanda de materiais,
advertências de importação e eventos pendentes do ERP.

## Executar

Requer Python 3.11 ou superior.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn danfer_os.main:app --reload
```

## Testes

```powershell
pytest
```
