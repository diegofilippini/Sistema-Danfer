# Matriz de consolidação 1.3.0

| Área | Evidência no sistema | Situação |
|---|---|---|
| Comercial e proposta | editor multi-itens, revisões, PDF A4, Danfer/DF | Consolidado |
| Custos | venda/serviço, margem, lote de dobra, calandra tempo/peso | Consolidado |
| Engenharia | materiais/ERP, Biblioteca, lote DXF, itens de orçamento e nesting visual | Consolidado |
| PCP | OP persistente, capacidade diária, calendário e apontamentos | Consolidado |
| Custos reais | material, processo, terceiro, qualidade automática por OP e desvio percentual | Consolidado |
| ERP | orçamento aprovado, pedidos, códigos, empresa, payload, tentativas e erro persistente | Adaptador local consolidado |
| Solicitações | numeração, prioridade, responsável, histórico e vínculo | Consolidado |
| Comunicação | rascunhos e links WhatsApp/e-mail rastreáveis | Consolidado sem envio automático |
| Segurança | autenticação, perfis por rota, senha e backup | Consolidado para uso local |
| Identidade | cores, assinatura institucional, contatos e QR Code | Recriada; logotipo oficial não fornecido |

## Limites que dependem de insumos externos

- A sincronização online com o ERP requer contrato da API, URL e credenciais do fornecedor.
- Push móvel requer hospedagem HTTPS e credenciais FCM/Web Push.
- Os CNPJs e endereços fiscais de Danfer/DF devem ser preenchidos nos perfis de faturamento.
- O logotipo vetorial e o banner fotográfico oficiais não foram fornecidos; o sistema usa a identidade geométrica reconstruída.
- O nesting geométrico e a prévia SVG estão disponíveis; geração de programa CNC depende do pós-processador/equipamento.
