FROM python:3.11-slim

# Define diretório de trabalho
WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copia arquivos de requisitos
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY mcp_server.py .

# Define variáveis de ambiente padrão
ENV ANYPOINT_URL=https://anypoint.mulesoft.com
ENV CLIENT_ID=preencher
ENV CLIENT_SECRET=preencher
ENV ORG_ID=preencher

# Torna o script executável
RUN chmod +x mcp_server.py

# Expõe porta (stdio não precisa, mas para debug)
EXPOSE 8000

# Comando para executar o servidor
CMD ["python", "mcp_server.py"]
