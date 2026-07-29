# Arquitetura inicial

## Objetivos

- Manter uma única fonte de verdade para regras industriais e comerciais.
- Entregar incrementos pequenos, testáveis e reversíveis.
- Separar API, regras de negócio, persistência e interfaces.
- Preparar a aplicação para PWA e futuras notificações móveis.

## Estrutura

```text
src/danfer_os/
  main.py        composição da aplicação
  routers/       contratos HTTP
tests/           testes automatizados
docs/            decisões técnicas e funcionais
```

Os próximos módulos deverão introduzir camadas de domínio e persistência sem
colocar regras de negócio diretamente nas rotas HTTP.

## Próximas decisões

1. Autenticação, troca obrigatória de senha e perfis de acesso.
2. PostgreSQL em produção e banco isolado para testes.
3. Migrações de banco versionadas.
4. Frontend web responsivo e instalável como PWA.

