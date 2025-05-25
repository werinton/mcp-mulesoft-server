# ADVERTÊNCIA
Este projeto foi criado em uma tarde chuvosa de sábado qualquer por alguém que não sabe programar em Python. Logo, não o use em produção — não que você não possa, mas não deveria. Crie uma conta trial e faça os testes. Caso goste da ideia, solicite que alguém que saiba o que está fazendo crie um servidor MCP ou revise este código, corrigindo qualquer falha de segurança que ele possa apresentar.

# MCP Server para MuleSoft Exchange

Este é um servidor MCP (Model Context Protocol) que expõe as APIs catalogadas no MuleSoft Exchange, permitindo consultas em linguagem natural sobre as APIs disponíveis.

## Funcionalidades

- **Busca de APIs**: Encontra APIs por termo de pesquisa ou funcionalidade
- **Detalhes de APIs**: Obtém informações completas sobre uma API específica  
- **Especificações OpenAPI/RAML**: Extrai e analisa especificações técnicas das APIs
- **Análise de Endpoints**: Analisa endpoints e operações disponíveis
- **Busca por Categoria**: Localiza APIs por categoria funcional (banking, payment, etc.)
- **Autenticação Automática**: Usa Connected Apps para autenticação no MuleSoft

## Configuração das Credenciais

### 1. Obter Credenciais do Connected App no MuleSoft

1. **Acesse o Anypoint Platform**:
   - Faça login em https://anypoint.mulesoft.com
   - Vá para **Access Management** → **Connected Apps**

2. **Criar um Connected App**:
   ```
   - Clique em "Create Connected App"
   - Name: "MCP Integration" (ou nome de sua escolha)
   - Grant Types: ✓ Client Credentials
   - Scopes: 
     ✓ Exchange Viewer
   ```

3. **Copiar as Credenciais**:
   - **Client ID**: Será usado como `CLIENT_ID`
   - **Client Secret**: Será usado como `CLIENT_SECRET`

### 2. Obter Organization ID

1. **Via Interface Web**:
   - No Anypoint Platform, vá para **Access Management** → **Organization**
   - O Organization ID aparecerá na URL ou nas configurações da organização

2. **Via API** (alternativo):
   ```bash
   curl -X GET "https://anypoint.mulesoft.com/accounts/api/profile" \
        -H "Authorization: Bearer SEU_TOKEN"
   ```

## Configuração no Claude Desktop

### 1. Localizar o Arquivo de Configuração

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Linux:**
```
~/.config/Claude/claude_desktop_config.json
```

### 2. Configurar o MCP Server

Edite o arquivo `claude_desktop_config.json` e adicione:

```json
{
  "mcpServers": {
    "mulesoft-exchange": {
      "command": "python",
      "args": ["/caminho/para/seu/projeto/mcp_server.py"],
      "env": {
        "ANYPOINT_URL": "https://anypoint.mulesoft.com",
        "CLIENT_ID": "SUA_CLIENT_ID_AQUI",
        "CLIENT_SECRET": "SEU_CLIENT_SECRET_AQUI", 
        "ORG_ID": "SEU_ORG_ID_AQUI",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### 3. Exemplo Completo de Configuração

```json
{
  "mcpServers": {
    "mulesoft-exchange": {
      "command": "python",
      "args": ["/Users/seuusuario/projetos/mulesoft-mcp/mcp_server.py"],
      "env": {
        "ANYPOINT_URL": "https://anypoint.mulesoft.com",
        "CLIENT_ID": "4cdfxxxxxxxx",
        "CLIENT_SECRET": "b4ADdxxx8c4E8FbxxxxxxxEBbFfbe56",
        "ORG_ID": "489d3dee-ffff-4ee0-xxxx-sdfsdffsd",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### 4. Configuração com Docker (Recomendado)

Se preferir usar Docker, configure assim:

```json
{
  "mcpServers": {
    "mulesoft-exchange": {
      "command": "docker",
      "args": [
        "run", 
        "--rm", 
        "-i",
        "--env", "CLIENT_ID=SUA_CLIENT_ID_AQUI",
        "--env", "CLIENT_SECRET=SEU_CLIENT_SECRET_AQUI",
        "--env", "ORG_ID=SEU_ORG_ID_AQUI",
        "--env", "LOG_LEVEL=INFO",
        "mulesoft-mcp-server"
      ]
    }
  }
}
```

## Instalação e Execução

### Opção 1: Docker (Recomendado)

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/mulesoft-mcp-server.git
cd mulesoft-mcp-server

# 2. Configure as variáveis no docker-compose.yml
# Edite o arquivo e substitua as credenciais

# 3. Construir e executar
docker-compose up --build

# Para debug (com porta HTTP exposta)
docker-compose --profile debug up --build
```

### Opção 2: Instalação Local

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/mulesoft-mcp-server.git
cd mulesoft-mcp-server

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
export CLIENT_ID="sua_client_id"
export CLIENT_SECRET="seu_client_secret"
export ORG_ID="seu_org_id"

# 4. Executar servidor
python mcp_server.py
```

### Opção 3: Ambiente Virtual Python

```bash
# 1. Criar ambiente virtual
python -m venv mulesoft-mcp-env
source mulesoft-mcp-env/bin/activate  # Linux/Mac
# ou
mulesoft-mcp-env\Scripts\activate     # Windows

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar e executar
export CLIENT_ID="sua_client_id"
export CLIENT_SECRET="seu_client_secret"  
export ORG_ID="seu_org_id"
python mcp_server.py
```

## Verificação da Configuração

### 1. Reiniciar o Claude Desktop

Após editar o arquivo de configuração, feche completamente e reabra o Claude Desktop.

### 2. Verificar Logs

**No diretório do projeto:**
```bash
tail -f logs/mcp_server.log
```

**Ou via Docker:**
```bash
docker-compose logs -f mulesoft-mcp
```

### 3. Testar no Claude

Digite no Claude:
```
"Mostre-me as APIs disponíveis no MuleSoft Exchange"
```

Se configurado corretamente, você verá o MCP sendo executado nos logs.

## Exemplos de Uso no Claude

### Perguntas que você pode fazer:

1. **"Qual API devo usar para efetuar cash in em uma conta corrente?"**
   - O servidor buscará APIs relacionadas a "cash", "account", "banking"

2. **"Que APIs temos disponíveis para pagamentos?"**
   - Buscará por APIs com termos relacionados a "payment", "pay", "transaction"

3. **"Mostre detalhes da API de banking"**
   - Listará detalhes específicos da API de banking incluindo endpoints

4. **"Analise os endpoints da API banking"**
   - Extrairá e analisará a especificação OpenAPI/RAML da API

5. **"Quais conectores temos para integração?"**
   - Mostrará conectores disponíveis no Exchange

6. **"Me mostre a especificação OpenAPI da API de payments"**
   - Baixará e exibirá a especificação completa da API

## Ferramentas Disponíveis

### Core Tools:
- `search_apis`: Busca APIs por termo de pesquisa
- `get_api_details`: Obtém detalhes completos de uma API específica
- `find_apis_by_category`: Encontra APIs por categoria funcional

### Advanced Tools:
- `get_api_specification`: Obtém especificação OpenAPI/RAML detalhada
- `get_api_files`: Lista todos os arquivos de uma API
- `analyze_api_endpoints`: Analisa endpoints e operações disponíveis

### Recursos Expostos:
- `mulesoft://apis`: Lista de todas as APIs
- `mulesoft://connectors`: Lista de conectores

## Configuração Avançada

### Variáveis de Ambiente Disponíveis:

```bash
# Obrigatórias
CLIENT_ID=                    # Client ID do Connected App
CLIENT_SECRET=                # Client Secret do Connected App  
ORG_ID=                      # Organization ID do MuleSoft

# Opcionais
ANYPOINT_URL=https://anypoint.mulesoft.com  # URL base do Anypoint
LOG_LEVEL=INFO               # Nível de log (DEBUG, INFO, WARNING, ERROR)
```

### Configuração de Log Detalhado:

Para debug mais detalhado, use:
```bash
export LOG_LEVEL=DEBUG
```

Ou no Claude config:
```json
"env": {
  "LOG_LEVEL": "DEBUG"
}
```

## Troubleshooting

### Problema: "Falha na autenticação"

**Soluções:**
1. Verificar se `CLIENT_ID` e `CLIENT_SECRET` estão corretos
2. Verificar se o Connected App tem os scopes necessários
3. Verificar conectividade com https://anypoint.mulesoft.com

### Problema: "Organization not found"

**Soluções:**
1. Verificar se `ORG_ID` está correto
2. Verificar se o usuário/Connected App tem acesso à organização

### Problema: "Claude não reconhece o MCP"

**Soluções:**
1. Verificar se o caminho para `mcp_server.py` está correto
2. Verificar se Python está instalado e acessível
3. Verificar logs do Claude Desktop
4. Reiniciar o Claude Desktop completamente

### Problema: "Dependências não encontradas"

**Soluções:**
1. Usar ambiente virtual Python
2. Verificar se todas as dependências foram instaladas:
   ```bash
   pip install -r requirements.txt
   ```
3. Usar a versão Docker que já tem tudo configurado

## Como Funciona

1. **Autenticação**: O servidor se autentica automaticamente no MuleSoft usando Connected Apps (OAuth2 Client Credentials)
2. **Busca**: Quando você faz uma pergunta, o Claude usa as ferramentas MCP para buscar APIs relevantes
3. **Extração**: Para especificações detalhadas, baixa e extrai arquivos ZIP do Exchange
4. **Análise**: Processa especificações OpenAPI/RAML para extrair endpoints e operações
5. **Resposta**: Retorna informações formatadas e estruturadas sobre as APIs encontradas
6. **Renovação**: O token de acesso é renovado automaticamente quando necessário

## Estrutura do Projeto

```
.
├── mcp_server.py              # Servidor MCP principal
├── requirements.txt           # Dependências Python  
├── Dockerfile                 # Configuração Docker
├── docker-compose.yml         # Orquestração Docker
├── logs/                      # Diretório de logs
│   └── mcp_server.log        # Log do servidor
├── docs/                      # Documentação adicional
│   ├── postman_collection.json # Collection Postman de referência
│   └── environment.json       # Environment Postman
└── README.md                  # Esta documentação
```

## Segurança

### Boas Práticas:

1. **Nunca comitar credenciais** no código
2. **Usar variáveis de ambiente** para credenciais sensíveis
3. **Rotacionar Connected App secrets** periodicamente
4. **Usar princípio do menor privilégio** nos scopes do Connected App
5. **Monitorar logs** para atividades suspeitas

### Exemplo de .gitignore:

```gitignore
# Credenciais
.env
*.env
claude_desktop_config.json

# Logs
logs/
*.log

# Python
__pycache__/
*.pyc
venv/
```

## Limitações Conhecidas

- Limita resultados a 50 APIs por busca (configurável)
- Cache de token básico sem persistência
- Não implementa rate limiting avançado
- Extração de ZIP suporta apenas YAML/JSON básicos
- Análise de RAML limitada (foco em OpenAPI)

## Contribuição

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

## Licença

Este projeto está licenciado sob a MIT License - veja o arquivo LICENSE para detalhes.

## Exemplo Prático de Integração

### Configuração Completa Passo a Passo:

1. **Obter credenciais MuleSoft** (Connected App)
2. **Instalar o servidor MCP** (Docker ou local)
3. **Configurar Claude Desktop** com as credenciais
4. **Testar integração** com perguntas no Claude

### Exemplo de Sessão no Claude:

```
👤 Usuário: "Preciso integrar um sistema de pagamentos, que APIs vocês têm?"

🤖 Claude: [executa search_apis com termo "payment"]
   "Encontrei 3 APIs relacionadas a pagamentos:
   
   1. **Payment Gateway API** (v2.1)
      - Tipo: rest-api  
      - Descrição: API principal para processamento de pagamentos...
      - ID: 489d3dee-17ec-4ee0-bad8-b1b8ea4799cc/payment-gateway
   
   2. **Direct Payment API** (v1.5)
      - Tipo: rest-api
      - Descrição: API para pagamentos diretos...
   
   Gostaria de ver detalhes específicos de alguma dessas APIs?"

👤 Usuário: "Me dê mais detalhes e a especificação da Payment Gateway API"

🤖 Claude: [executa get_api_details e get_api_specification]
   "**Detalhes da Payment Gateway API v2.1:**
   
   - **Tipo:** REST API
   - **Endpoints principais:**
     - POST /payments - Criar pagamento
     - GET /payments/{id} - Consultar pagamento  
     - PUT /payments/{id}/cancel - Cancelar pagamento
   
   **Especificação OpenAPI:**
   ```json
   {
     "openapi": "3.0.0",
     "info": {
       "title": "Payment Gateway API",
       "version": "2.1.0"
     },
     "paths": {
       "/payments": {
         "post": {
           "summary": "Create new payment",
           ...
   ```

   Esta API permite processar pagamentos com suporte a múltiplos métodos..."
```

Este exemplo mostra como o Claude pode acessar e analisar automaticamente as APIs do seu catálogo MuleSoft para responder perguntas específicas sobre integração.