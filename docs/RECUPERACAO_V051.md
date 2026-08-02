# Recuperação seletiva da v0.51

Fonte analisada: `Danfer_Industrial_OS_Prototipo_v0_51_Consolidada_Testes.zip`.

## Regra de consolidação

A v0.51 é um protótipo monolítico em HTML/JavaScript com persistência em `localStorage`. A versão atual possui API FastAPI, modelos validados, armazenamento no servidor e testes automatizados. Portanto, a recuperação será funcional e seletiva; os arquivos antigos não serão simplesmente copiados sobre a aplicação atual.

Devem ser preservados na versão atual:

- cálculo comercial e industrial vigente;
- nesting básico e avançado, incluindo NcAv e aproveitamento por item;
- margem configurável por item;
- materiais, operações ERP e roteiros padrão em Manutenções;
- novo gerador de proposta comercial baseado no PDF aprovado;
- autenticação, backup e restauração do servidor;
- suíte de testes existente.

## Inventário dos módulos

| Módulo v0.51 | Situação atual | Ação de recuperação |
|---|---|---|
| Painel do dia | Parcial | Expandir o dashboard com prioridades, atrasos, liberações e qualidade aberta. |
| Centro de negociações | Parcial | Consolidar CRM, funil, atividades, próximo contato e orçamento relacionado. |
| Orçamentos | Presente | Preservar e complementar ações comerciais. |
| Novo orçamento | Presente e mais recente | Preservar cálculo, nesting, roteiros e novo PDF. |
| Liberação PCP | Parcial | Criar tela de validação e liberação seletiva para geração de OPs. |
| Pedidos diretos (SP) | Ausente | Migrar solicitação direta e entrada na programação. |
| Central de programação | Parcial | Expandir PCP com filtros, reserva de capacidade e avanço de processo. |
| Arquivo de OPs | Ausente | Criar consulta, filtros, seleção e impressão. |
| Acompanhamento do fluxo | Parcial | Criar visão consolidada por orçamento, OP, estágio e progresso. |
| Qualidade e custos | Parcial | Integrar perdas, horas, terceiros e custo real da OP. |
| Dashboard qualidade | Ausente | Criar indicadores por processo, custo, reincidência e horas. |
| Análise de desvios | Parcial | Expandir comparação para item, processo, motivo e situação. |
| Engenharia de produtos | Parcial | Unificar biblioteca, DXF, BOM e custeio de produto. |
| Solicitações de status | Parcial | Vincular solicitações à OP, previsão, progresso e SLA. |
| Dashboards gerenciais | Ausente | Criar visão consolidada comercial, produção, qualidade e rentabilidade. |
| Análise mensal | Ausente | Criar filtros e exportação CSV com dados reais. |
| Auditoria | API sem tela | Criar filtros e exportação da trilha persistida. |
| Manutenções detalhadas | Parcial | Recuperar cadastros configuráveis faltantes e manter acesso administrativo. |
| Usuários e permissões | Parcial | Revisar perfis, permissões por módulo e preferências. |
| Backup/restauração | API sem tela | Recolocar controles administrativos na interface. |
| Busca global e notificações | Ausente/parcial | Recuperar busca por cliente, orçamento, OP e solicitação. |

## Etapas

1. Preservação e inventário: concluída.
2. Cadastros e Manutenções: recuperar parâmetros e entidades compartilhadas.
3. Operação: liberação PCP, pedidos diretos, programação, arquivo de OPs e fluxo.
4. Qualidade e gestão: custos, dashboards, desvios, análise mensal e auditoria.
5. Comercial e experiência: CRM completo, busca global, notificações e permissões.
6. Validação: migração de dados de teste, testes automatizados, teste web e pacote final.

Cada etapa deve manter compatibilidade com os dados da versão atual e incluir testes antes da consolidação no GitHub.
