# Danfer Industrial OS 1.0.0 — Guia operacional

## Inicialização e acesso

No Windows, execute `INICIAR_WEB.bat`. O sistema abre em
`http://127.0.0.1:8000`. O acesso inicial de testes é `admin` / `Danfer@2026`;
troque a senha após o primeiro acesso.

## Rotina recomendada

1. Cadastre clientes em **CRM / Clientes**.
2. Mantenha materiais, preços, espessuras e operações em **Engenharia / DXF**.
3. Importe o DXF; a análise cria um registro pesquisável na Biblioteca Técnica.
4. Monte a estrutura BOM e crie/libere a ordem de produção.
5. Consulte carga e capacidade no **PCP diário**, ajustando exceções do calendário pela API quando necessário.
6. Registre apontamentos de operação, material, terceiro e qualidade na OP.
7. Acompanhe a comparação de custo estimado versus realizado.
8. Use a Central de Solicitações para demandas entre Comercial, PCP e Engenharia.
9. Prepare mensagens; o sistema gera o link de WhatsApp/e-mail, mas não envia sem ação do usuário.

## Orçamentos e propostas

- Venda e serviço possuem cálculo próprio; serviço ignora matéria-prima.
- A margem padrão recuperada é 30%, com margem opcional por item.
- Calandra aceita custeio por tempo ou por peso.
- Venda destaca somente IPI; serviço apresenta o valor final sem linha tributária.
- Escolha Danfer ou DF como unidade de faturamento.
- A proposta PDF inclui contato e QR Code do WhatsApp institucional.

## Segurança, dados e recuperação

- As APIs operacionais exigem login e aplicam perfis por módulo.
- Os dados ficam em arquivos JSON dentro de `data/`.
- Administradores podem baixar um ZIP em `/api/v1/system/backup`.
- A restauração global usa `POST /api/v1/system/restore` com o ZIP; o sistema
  valida o conteúdo, cria uma cópia `pre-restore` e informa que deve ser reiniciado.
- Guarde backups fora da pasta da aplicação antes de atualizar ou mover o sistema.
- O pacote não configura HTTPS nem acesso público; use somente em máquina/rede confiável até uma implantação segura.

## Perfis

- Administrador: configuração e acesso integral.
- Comercial: CRM, orçamentos, faturamento, solicitações e comunicação.
- Engenharia: Biblioteca Técnica, DXF, materiais e importações.
- PCP/Produção: programação, capacidade, OPs e apontamentos.
- Qualidade: ocorrências e participação em solicitações.
- Consulta: leitura da Biblioteca Técnica e painéis não restritos.

## Validação técnica

Execute `pytest` no ambiente virtual. A documentação interativa da API fica em
`http://127.0.0.1:8000/docs`.
