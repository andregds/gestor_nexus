# 📊 Nexus Monitor - Gestor de Disponibilidade e Clientes

> Um sistema completo para monitoramento de serviços web (DNS/HTTP) e gestão de clientes, com notificações automáticas via WhatsApp e Telegram.

![Status](https://img.shields.io/badge/Status-Em_Desenvolvimento-yellow)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-009688.svg)
![License](https://img.shields.io/badge/License-MIT-green)

## 📝 Sobre o Projeto

O **Nexus Monitor** foi desenvolvido para resolver dois problemas principais: monitorar a estabilidade de servidores/URLs em tempo real e gerenciar a base de clientes de serviços digitais (como IPTV, Streaming ou SaaS).

O sistema verifica periodicamente o status dos serviços e, em caso de queda ou lentidão, notifica o administrador via WhatsApp (integração com Evolution API) e Telegram. Além disso, permite o cadastro de clientes com datas de vencimento, enviando lembretes automáticos de cobrança.

## ✨ Funcionalidades Principais

### 🖥️ Monitoramento
- **Verificação em Tempo Real:** Checagem de status HTTP (200, 404, 500, etc.) e latência (ping).
- **Alertas Inteligentes:** Notificações imediatas quando um serviço cai (DOWN) ou volta (UP).
- **Histórico:** Registro da última verificação com data e hora precisas.

### 👥 Gestão de Clientes
- **CRUD Completo:** Cadastro, edição e remoção de clientes.
- **Controle de Vencimento:** Monitoramento de datas de expiração de assinaturas.
- **Lembretes Automáticos:** Envio de mensagens de cobrança via WhatsApp antes e depois do vencimento.

### 🔔 Notificações & Integrações
- **WhatsApp (Evolution API):** Conexão via QR Code diretamente pelo painel. Suporte a envio de mensagens de texto e alertas.
- **Telegram Bot:** Integração nativa para receber alertas de infraestrutura em grupos ou privado.
- **Configurações Personalizadas:** O usuário escolhe quais tipos de alerta deseja receber (Queda, Volta, Lentidão).

## 🛠️ Tecnologias Utilizadas

### Backend
- **Python 3.x**
- **FastAPI:** Framework moderno e de alta performance para construção da API.
- **SQLAlchemy:** ORM para interação com o banco de dados.
- **SQLite:** Banco de dados leve (padrão), facilmente migrável para PostgreSQL/MySQL.
- **Uvicorn:** Servidor ASGI.

### Frontend
- **HTML5 / CSS3:** Interface limpa, responsiva e moderna.
- **JavaScript (Vanilla):** Lógica de interação com a API (Fetch), SPA (Single Page Application) para navegação fluida.

## 🚀 Como Executar o Projeto

### Pré-requisitos
- Python instalado.
- Uma instância da [Evolution API](https://github.com/EvolutionAPI/evolution-api) rodando (para funcionalidades de WhatsApp).

### Passo a Passo

1. **Clone o repositório**

2. **Crie e ative um ambiente virtual**
3. **Instale as dependências**
4. **Configure as Variáveis de Ambiente**
   Crie um arquivo `.env` na raiz do projeto (baseado no exemplo abaixo) e preencha com seus dados:
5. **Execute o Servidor**
   Navegue até a pasta do backend (se necessário) e rode:
6. **Acesse o Sistema**
   Abra o navegador em: `http://localhost:8000/frontend/login.html`

## 📂 Estrutura do Projeto
🤝 ContribuiçãoContribuições são bem-vindas! Sinta-se à vontade para abrir issues ou enviar pull requests.1.Faça um Fork do projeto2.Crie uma Branch para sua Feature (git checkout -b feature/MinhaFeature)3.Faça o Commit (git commit -m 'Add: Minha nova feature')4.Faça o Push (git push origin feature/MinhaFeature)5.Abra um Pull Request


📄 LicençaEste projeto está sob a licença MIT. Veja o arquivo LICENSE para mais detalhes.