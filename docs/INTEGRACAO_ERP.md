# Integração ERP — contrato de homologação 1.7.0

Esta versão usa uma fila transacional e independente de fornecedor. Nenhum evento
é enviado à internet enquanto a integração estiver desabilitada. O fornecedor do
ERP deve mapear o contrato canônico abaixo para sua API durante a homologação.

## Dados enviados

### Empresa e pedido

- unidade de faturamento Danfer/DF e código da empresa no ERP;
- número/revisão do orçamento, pedido de compra do cliente e vendedor;
- natureza de operação e respectivo código ERP;
- modalidade comercial, entrega, frete, responsável pelo frete e transportadora;
- subtotal, desconto, frete, tributos e total;
- percentuais de IPI, CBS e IBS e cenário tributário.

### Cliente

- código ERP, razão social, CNPJ/CPF, IE, IM e SUFRAMA;
- regime tributário, contatos, telefone e e-mails comercial/fiscal;
- logradouro, número, complemento, bairro, cidade, UF, CEP e país;
- condição de pagamento/código ERP e limite de crédito.

### Produtos e serviços

- código, descrição, unidade, quantidade e valor unitário/total;
- peso líquido/bruto, material e espessura;
- quantidade efetivamente faturada em cada remessa parcial;
- referência do orçamento e sequência da remessa para idempotência.

### Financeiro e boletos

- parcelas com sequência, vencimento, valor e meio de pagamento;
- código da condição de pagamento;
- conta bancária, carteira de cobrança, centro de custo e categoria financeira;
- indicação para geração de boleto e instruções por parcela;
- conferência obrigatória de que a soma das parcelas coincide com o faturamento.

Na ausência de parcelas manuais, o sistema interpreta condições como `28/35/42
DDL`, divide o total com ajuste de centavos na última parcela e sugere boleto.

### Estoque de matérias-primas

- código ERP da matéria-prima, especificação e espessura;
- depósito, unidade de estoque e quantidade requerida;
- consumo calculado com o aproveitamento/nesting aplicado no orçamento;
- agregação por código e depósito para impedir movimentos duplicados;
- ausência de baixa para industrialização com material do cliente/terceiros.

Cada material deve possuir código ERP, depósito, unidade de estoque, unidade de
compra, fator de conversão, NCM e origem fiscal nas Manutenções.

## Fluxo recomendado

1. Preencher **Integrações > Configuração da integração ERP**.
2. Completar códigos ERP dos clientes, materiais, produtos, operações, natureza,
   empresa, transportadora, financeiro e depósitos.
3. Consultar `GET /api/v1/integrations/erp/readiness`.
4. Gerar pedido/faturamento e validar o evento em
   `GET /api/v1/integrations/erp/events/{id}/validate`.
5. Enviar em homologação usando o endpoint do fornecedor.
6. Confirmar resultado em `POST /api/v1/integrations/erp/events/{id}/ack`.
7. Somente depois dos testes de pedido, nota, boleto, estoque, cancelamento e
   reprocessamento, habilitar a integração de produção.

## Pendências externas obrigatórias

Para transmissão real ainda são necessários: nome/versão do ERP, documentação
da API, URL de homologação, credenciais, códigos das empresas Danfer/DF, séries e
modelos fiscais, regras de CFOP/CST/CSOSN/NCM, depósitos, contas/carteiras,
transportadoras, vendedores, centros de custo e categorias financeiras.

Credenciais nunca devem ser incluídas em commits, ZIPs ou capturas de tela.
