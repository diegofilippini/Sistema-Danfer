# Danfer Industrial OS

## Versões para teste

- **Web:** execute `INICIAR_WEB.bat` e abra `http://127.0.0.1:8000`.
- **Windows:** execute `INICIAR_WEB.bat`; na primeira execução o ambiente é
  preparado e o navegador é aberto automaticamente.

A versão consolidada é a `1.3.0`, com interface responsiva, persistência local,
controle de acesso por perfil e API integrada.

### Acesso para testes

- Usuário: `admin`
- Senha: `Danfer@2026`

Na primeira execução dos pacotes de teste, o sistema cria dados demonstrativos
de cliente, orçamento, peças, BOM, ordem de produção, qualidade e manutenção.

## Versão 1.3.0 — Consolidação por fases

Inclui custeio avançado por chapa/faixa, troca obrigatória da senha inicial e um
gerador determinístico de 20 orçamentos aprovados para homologação do fluxo
Comercial → ERP → PCP e da comparação entre custos estimados e realizados.

- CRM e cadastro de clientes;
- orçamento de venda e serviço;
- custos de matéria-prima, processos, terceiros e indiretos;
- margem, IPI e preparação para CBS/IBS;
- revisões, negociação, aprovação e proposta em PDF;
- análise geométrica de DXF e sugestão NcAv;
- regras de nesting e perdas configuráveis;
- Biblioteca Técnica, BOM, PCP e integrações;
- Qualidade, Manutenção, Auditoria e notificações;
- usuários e perfis;
- PWA preparada para instalação.

Também foram consolidados o editor multi-itens, custeio de serviço sem matéria-prima,
calandra por tempo/peso, catálogo de materiais e operações ERP, registro de DXF na
Biblioteca Técnica, PCP diário com capacidade/calendário, custos estimados versus
realizados, faturamento Danfer/DF, Central de Solicitações e preparação de mensagens
para WhatsApp/e-mail.

A versão 1.1 acrescenta importação DXF em lote para o orçamento e planejador
visual de nesting com rotação, verificação de encaixe e comparação entre chapas
1200 × 3000 e 1500 × 3000.

A versão 1.2 integra orçamento aprovado à fila ERP e à OP, transporta custos
estimados, apropria custos de qualidade automaticamente e direciona notificações
por usuário ou perfil.

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
