@echo off
cd /d "D:\GOOGLE DRIVE\Material_de_estudo\PythonProject\Sistema de Monitoramento de DNS com Notificações WhatsApp"

echo === Git Status ===
git status

echo === Creating branch feature-flags-sidebar-v2.4 ===
git checkout -b feature-flags-sidebar-v2.4

echo === Adding all files ===
git add -A

echo === Committing ===
git commit -m "feat: Padronizacao sidebar com feature flags e otimizacao de carregamento v2.4

- Adicionado CSS preload para evitar flash de elementos desabilitados
- Otimizado sidebar.js para carregamento rapido (usa localStorage primeiro)
- Padronizado estrutura de sidebar em todas as paginas HTML
- Todos os links agora tem data-feature-key para controle de visibilidade
- Menu Clientes e Produtos agora sao grupos sanfonados em todas as paginas
- Busca flags do servidor em background (nao bloqueia renderizacao)"

echo === Pushing to origin ===
git push -u origin feature-flags-sidebar-v2.4

echo === Done ===
pause

