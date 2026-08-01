# Matriz de consolidação 1.0.0

| Área | Evidência no sistema | Situação |
|---|---|---|
| Comercial e proposta | editor multi-itens, revisões, PDF A4, Danfer/DF | Consolidado |
| Custos | venda/serviço, margem, lote de dobra, calandra tempo/peso | Consolidado |
| Engenharia | materiais/ERP, Biblioteca Técnica, análise e registro DXF | Consolidado |
| PCP | OP persistente, capacidade diária, calendário e apontamentos | Consolidado |
| Custos reais | material, processo, terceiro, qualidade e desvio percentual | Consolidado |
| ERP | pedidos, códigos, empresa, payload, tentativas e erro persistente | Adaptador local consolidado |
| Solicitações | numeração, prioridade, responsável, histórico e vínculo | Consolidado |
| Comunicação | rascunhos e links WhatsApp/e-mail rastreáveis | Consolidado sem envio automático |
| Segurança | autenticação, perfis por rota, senha e backup | Consolidado para uso local |
| Identidade | cores, assinatura institucional, contatos e QR Code | Recriada; logotipo oficial não fornecido |

## Limites que dependem de insumos externos

- A sincronização online com o ERP requer contrato da API, URL e credenciais do fornecedor.
- Push móvel requer hospedagem HTTPS e credenciais FCM/Web Push.
- Os CNPJs e endereços fiscais de Danfer/DF devem ser preenchidos nos perfis de faturamento.
- O logotipo vetorial e o banner fotográfico oficiais não foram fornecidos; o sistema usa a identidade geométrica reconstruída.
- Nesting CNC automático e geração de programa de máquina dependem do pós-processador/equipamento utilizado.
