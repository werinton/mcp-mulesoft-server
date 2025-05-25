#!/usr/bin/env python3
"""
MCP Server para expor APIs catalogadas no MuleSoft Exchange
Permite consultas em linguagem natural sobre APIs disponíveis
"""

import json
import os
import sys
import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx
from datetime import datetime, timedelta
import urllib.parse
import zipfile
import io
import tempfile

# MCP imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource, 
    Tool, 
    TextContent, 
    EmbeddedResource,
    LoggingLevel
)

# Configuração de logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Log inicial com informações do ambiente
logger.info("🚀 Iniciando MCP MuleSoft Server")
logger.info(f"🔧 Log Level: {log_level}")
logger.info(f"🌐 Anypoint URL: {os.getenv('ANYPOINT_URL', 'https://anypoint.mulesoft.com')}")
logger.info(f"🏢 Organization ID: {os.getenv('ORG_ID', 'apreencher')}")
logger.info(f"🔑 Client ID: {os.getenv('CLIENT_ID', 'apreencher')}")

class MuleSoftExchangeClient:
    """Cliente para interagir com o MuleSoft Exchange"""
    
    def __init__(self):
        self.base_url = os.getenv('ANYPOINT_URL', 'https://anypoint.mulesoft.com')
        self.client_id = os.getenv('CLIENT_ID', 'apreencher')
        self.client_secret = os.getenv('CLIENT_SECRET', 'apreencher')
        self.org_id = os.getenv('ORG_ID', 'apreencher')
        self.access_token = None
        self.token_expires_at = None
        self.httpx_client = httpx.AsyncClient(timeout=30.0)
        
    def _log_curl_command(self, method: str, url: str, headers: Dict[str, str] = None, 
                         data: Any = None, params: Dict[str, Any] = None):
        """Loga a requisição no formato curl"""
        curl_parts = ["curl", "-X", method.upper()]
        
        # Adicionar headers
        if headers:
            for key, value in headers.items():
                # Mascarar tokens sensíveis nos logs
                if 'authorization' in key.lower() and 'bearer' in value.lower():
                    masked_value = f"Bearer {value.split('Bearer ')[-1][:20]}..."
                    curl_parts.extend(["-H", f'"{key}: {masked_value}"'])
                else:
                    curl_parts.extend(["-H", f'"{key}: {value}"'])
        
        # Adicionar dados do body
        if data:
            if isinstance(data, dict):
                # Para dados JSON
                json_data = json.dumps(data, separators=(',', ':'))
                curl_parts.extend(["-d", f"'{json_data}'"])
            else:
                # Para dados form-encoded ou string
                curl_parts.extend(["-d", f"'{data}'"])
        
        # URL final - se já tem parâmetros, usar como está
        final_url = url
        if params and "?" not in url:
            # Só adicionar parâmetros se a URL ainda não os tiver
            clean_params = {k: v for k, v in params.items() if v is not None and str(v).strip() != ""}
            if clean_params:
                query_string = urllib.parse.urlencode(clean_params, doseq=True)
                final_url = f"{url}?{query_string}"
        
        curl_parts.append(f'"{final_url}"')
        
        # Logar o comando curl
        curl_command = " ".join(curl_parts)
        logger.info(f"🌐 CURL Command: {curl_command}")
        
        return curl_command
        
    async def authenticate(self) -> bool:
        """Autentica usando Connected Apps (Client Credentials)"""
        try:
            auth_url = f"{self.base_url}/accounts/api/v2/oauth2/token"
            auth_data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials"
            }
            
            # Log da requisição de autenticação (com dados mascarados)
            masked_data = {
                "client_id": self.client_id,
                "client_secret": f"{self.client_secret[:8]}...",
                "grant_type": "client_credentials"
            }
            self._log_curl_command("POST", auth_url, 
                                 {"Content-Type": "application/x-www-form-urlencoded"}, 
                                 masked_data)
            
            response = await self.httpx_client.post(auth_url, data=auth_data)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer
            
            logger.info("✅ Autenticação realizada com sucesso")
            logger.info(f"🔑 Token expires at: {self.token_expires_at}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro na autenticação: {e}")
            return False
    
    async def _ensure_authenticated(self):
        """Garante que o token está válido"""
        if not self.access_token or (self.token_expires_at and datetime.now() >= self.token_expires_at):
            await self.authenticate()
    
    async def get_headers(self) -> Dict[str, str]:
        """Retorna headers com autenticação"""
        await self._ensure_authenticated()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    async def search_assets(self, search_term: str = "", asset_types: List[str] = None) -> List[Dict]:
        """Busca assets no Exchange"""
        try:
            headers = await self.get_headers()
            
            if asset_types is None:
                asset_types = ["rest-api", "soap-api", "http-api", "api-group", "connector"]
            
            # Garantir que asset_types é uma lista
            if not isinstance(asset_types, list):
                asset_types = [asset_types]
            
            # Parâmetros base
            base_params = {
                "search": search_term,
                "organizationId": self.org_id,
                "offset": "0",
                "limit": "50",
                "includeSnapshots": "true"
            }
            
            url = f"{self.base_url}/exchange/api/v2/assets"
            
            # Construir parâmetros manualmente para suportar múltiplos 'types'
            query_params = []
            
            # Adicionar parâmetros base
            for key, value in base_params.items():
                if value is not None and str(value).strip() != "":
                    query_params.append(f"{key}={urllib.parse.quote(str(value))}")
            
            # Adicionar múltiplos parâmetros 'types'
            for asset_type in asset_types:
                if asset_type and asset_type.strip():  # Verificar se não está vazio
                    query_params.append(f"types={urllib.parse.quote(str(asset_type))}")
            
            # Construir URL final
            final_url = f"{url}?{'&'.join(query_params)}"
            
            # Log da requisição curl (passando a URL já construída)
            self._log_curl_command("GET", final_url, headers)
            
            # Fazer a requisição com a URL já construída
            response = await self.httpx_client.get(final_url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Debug: logar o tipo e estrutura da resposta
            logger.info(f"🔍 Response type: {type(data)}")
            logger.info(f"🔍 Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            
            # Tratar diferentes formatos de resposta
            assets = []
            if isinstance(data, list):
                # Se a resposta é uma lista direta
                assets = data
                logger.info(f"🔍 Response is a direct list with {len(assets)} items")
            elif isinstance(data, dict):
                # Se a resposta é um objeto
                if 'assets' in data:
                    assets = data.get('assets', [])
                    logger.info(f"🔍 Found 'assets' key with {len(assets)} items")
                elif 'data' in data:
                    assets = data.get('data', [])
                    logger.info(f"🔍 Found 'data' key with {len(assets)} items")
                elif 'items' in data:
                    assets = data.get('items', [])
                    logger.info(f"🔍 Found 'items' key with {len(assets)} items")
                else:
                    # Log todas as chaves disponíveis para debug
                    logger.warning(f"🔍 Unexpected response structure. Available keys: {list(data.keys())}")
                    # Se não encontrar chaves conhecidas, assumir que o data é a lista
                    assets = [data] if data else []
            else:
                logger.error(f"🔍 Unexpected response type: {type(data)}")
                assets = []
            
            logger.info(f"🔍 Search completed: found {len(assets)} assets for term '{search_term}' with types {asset_types}")
            return assets
            
        except Exception as e:
            logger.error(f"❌ Erro ao buscar assets: {e}")
            # Log mais detalhado para debug
            import traceback
            logger.error(f"❌ Stack trace: {traceback.format_exc()}")
            return []
    
    async def get_asset_details(self, group_id: str, asset_id: str, version: str = None) -> Optional[Dict]:
        """Obtém detalhes de um asset específico"""
        try:
            headers = await self.get_headers()
            
            # Se versão não foi especificada, buscar todas as versões primeiro
            if not version:
                # Buscar asset para obter a versão mais recente
                assets = await self.search_assets(asset_id)
                if assets:
                    # Procurar o asset específico
                    for asset in assets:
                        if (asset.get('groupId') == group_id and 
                            asset.get('assetId') == asset_id):
                            version = asset.get('version', '1.0.0')
                            break
                    
                    if not version:
                        version = assets[0].get('version', '1.0.0')
                else:
                    version = '1.0.0'
            
            # Endpoints possíveis para obter detalhes do asset
            detail_endpoints = [
                f"{self.base_url}/exchange/api/v2/assets/{group_id}/{asset_id}/{version}",
                f"{self.base_url}/exchange/api/v2/assets/{group_id}/{asset_id}",
                f"{self.base_url}/exchange/api/v1/assets/{group_id}/{asset_id}/{version}",
                f"{self.base_url}/exchange/api/v1/assets/{group_id}/{asset_id}"
            ]
            
            logger.info(f"📋 Buscando detalhes para {group_id}/{asset_id} v{version}")
            
            for endpoint in detail_endpoints:
                try:
                    self._log_curl_command("GET", endpoint, headers)
                    response = await self.httpx_client.get(endpoint, headers=headers)
                    
                    if response.status_code == 200:
                        asset_details = response.json()
                        logger.info(f"✅ Detalhes encontrados em: {endpoint}")
                        return asset_details
                        
                except Exception as e:
                    logger.debug(f"Endpoint {endpoint} falhou: {e}")
                    continue
            
            # Se não encontrou via API específica, procurar na lista de assets
            logger.info(f"🔍 Buscando {asset_id} na lista de assets...")
            assets = await self.search_assets(asset_id)
            for asset in assets:
                if (asset.get('groupId') == group_id and 
                    asset.get('assetId') == asset_id):
                    logger.info(f"✅ Asset encontrado na busca geral")
                    return asset
            
            logger.warning(f"⚠️ Nenhum detalhe encontrado para {asset_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Erro ao obter detalhes do asset {asset_id}: {e}")
            return None
    
    async def _download_and_extract_spec(self, external_link: str, classifier: str, main_file: str = None) -> Optional[Dict]:
        """Baixa e extrai especificação de um arquivo ZIP"""
        try:
            logger.info(f"📥 Baixando arquivo {classifier} de: {external_link[:100]}...")
            
            # Baixar o arquivo ZIP
            response = await self.httpx_client.get(external_link)
            response.raise_for_status()
            
            logger.info(f"✅ Arquivo baixado, tamanho: {len(response.content)} bytes")
            
            # Criar um objeto BytesIO com o conteúdo
            zip_content = io.BytesIO(response.content)
            
            # Abrir o arquivo ZIP
            with zipfile.ZipFile(zip_content, 'r') as zip_file:
                file_list = zip_file.namelist()
                logger.info(f"📁 Arquivos no ZIP: {file_list}")
                
                # Procurar pelo arquivo YAML/YML (prioridade para especificação)
                yaml_file = None
                json_file = None
                
                for file_name in file_list:
                    if file_name.lower().endswith(('.yaml', '.yml')):
                        yaml_file = file_name
                        logger.info(f"🎯 Arquivo YAML encontrado: {yaml_file}")
                    elif file_name.lower().endswith('.json'):
                        json_file = file_name
                        logger.info(f"📄 Arquivo JSON encontrado: {json_file}")
                
                # Se tem main_file especificado, usar ele
                if main_file and main_file in file_list:
                    target_file = main_file
                    logger.info(f"🎯 Usando arquivo principal especificado: {target_file}")
                elif yaml_file:
                    target_file = yaml_file
                    logger.info(f"🎯 Usando arquivo YAML: {target_file}")
                elif json_file:
                    target_file = json_file
                    logger.info(f"🎯 Usando arquivo JSON: {target_file}")
                elif file_list:
                    # Pegar o primeiro arquivo se não encontrar YAML/JSON
                    target_file = file_list[0]
                    logger.info(f"🎯 Usando primeiro arquivo: {target_file}")
                else:
                    logger.warning("⚠️ Nenhum arquivo encontrado no ZIP")
                    return None
                
                # Extrair e ler o conteúdo
                with zip_file.open(target_file) as spec_file:
                    content = spec_file.read().decode('utf-8')
                    
                    logger.info(f"✅ Conteúdo extraído, tamanho: {len(content)} caracteres")
                    
                    # Tentar fazer parse se for JSON
                    if target_file.lower().endswith('.json'):
                        try:
                            parsed_content = json.loads(content)
                            return {
                                'type': 'openapi_json',
                                'classifier': classifier,
                                'file_name': target_file,
                                'content': parsed_content,
                                'raw_content': content,
                                'files_in_zip': file_list
                            }
                        except json.JSONDecodeError:
                            pass
                    
                    # Retornar como YAML/texto
                    return {
                        'type': 'openapi_yaml',
                        'classifier': classifier,
                        'file_name': target_file,
                        'content': content,
                        'files_in_zip': file_list
                    }
                    
        except zipfile.BadZipFile:
            logger.error("❌ Arquivo não é um ZIP válido")
            return None
        except Exception as e:
            logger.error(f"❌ Erro ao baixar/extrair arquivo: {e}")
            return None

    async def get_asset_specification(self, group_id: str, asset_id: str, version: str = None) -> Optional[Dict]:
        """Obtém a especificação OpenAPI/RAML de um asset específico"""
        try:
            headers = await self.get_headers()
            
            # Se não foi fornecida uma versão, buscar a versão mais recente
            if not version:
                asset_details = await self.get_asset_details(group_id, asset_id)
                if asset_details:
                    version = asset_details.get('version', '1.0.0')
                else:
                    version = '1.0.0'
            
            logger.info(f"📋 Buscando especificação para {group_id}/{asset_id} v{version}")
            
            # Primeiro, obter os detalhes do asset para ver os arquivos disponíveis
            asset_details = await self.get_asset_details(group_id, asset_id, version)
            if asset_details and 'files' in asset_details:
                files = asset_details['files']
                logger.info(f"📁 Asset tem {len(files)} arquivo(s)")
                
                # Priorizar arquivos de especificação OpenAPI
                priority_order = ['oas', 'fat-oas', 'raml', 'fat-raml']
                
                for classifier in priority_order:
                    for file_info in files:
                        file_classifier = file_info.get('classifier', '')
                        packaging = file_info.get('packaging', '')
                        external_link = file_info.get('externalLink', '')
                        main_file = file_info.get('mainFile', '')
                        
                        if file_classifier == classifier and external_link:
                            logger.info(f"🎯 Processando arquivo {classifier} ({packaging})")
                            
                            if packaging == 'zip':
                                # Baixar e extrair ZIP
                                spec_result = await self._download_and_extract_spec(
                                    external_link, classifier, main_file
                                )
                                if spec_result:
                                    return spec_result
                            else:
                                # Arquivo direto (não ZIP)
                                try:
                                    spec_response = await self.httpx_client.get(external_link)
                                    if spec_response.status_code == 200:
                                        content_type = spec_response.headers.get('content-type', '')
                                        
                                        if 'application/json' in content_type:
                                            try:
                                                spec_data = spec_response.json()
                                                return {
                                                    'type': 'openapi_json',
                                                    'classifier': classifier,
                                                    'content': spec_data,
                                                    'content_type': content_type
                                                }
                                            except:
                                                pass
                                        
                                        return {
                                            'type': 'openapi_yaml',
                                            'classifier': classifier,
                                            'content': spec_response.text,
                                            'content_type': content_type
                                        }
                                        
                                except Exception as e:
                                    logger.debug(f"Erro ao baixar arquivo direto {external_link}: {e}")
                                    continue
            
            # Fallback: tentar endpoints tradicionais se não encontrou arquivos
            spec_endpoints = [
                f"{self.base_url}/exchange/api/v2/assets/{group_id}/{asset_id}/{version}/files",
                f"{self.base_url}/exchange/api/v2/assets/{group_id}/{asset_id}/{version}/fat-raml",
                f"{self.base_url}/exchange/api/v2/assets/{group_id}/{asset_id}/{version}/instances",
                f"{self.base_url}/exchange/api/v1/assets/{group_id}/{asset_id}/{version}/raml",
                f"{self.base_url}/exchange/api/v1/assets/{group_id}/{asset_id}/{version}/oas"
            ]
            
            for endpoint in spec_endpoints:
                try:
                    self._log_curl_command("GET", endpoint, headers)
                    response = await self.httpx_client.get(endpoint, headers=headers)
                    
                    if response.status_code == 200:
                        content_type = response.headers.get('content-type', '')
                        
                        # Verificar se é JSON ou YAML/RAML
                        if 'application/json' in content_type:
                            spec_data = response.json()
                            return {
                                'type': 'api_endpoint',
                                'content': spec_data,
                                'content_type': content_type,
                                'endpoint': endpoint
                            }
                        else:
                            return {
                                'type': 'api_endpoint',
                                'content': response.text,
                                'content_type': content_type,
                                'endpoint': endpoint
                            }
                        
                except Exception as e:
                    logger.debug(f"Endpoint {endpoint} falhou: {e}")
                    continue
            
            logger.warning(f"⚠️ Nenhuma especificação encontrada para {asset_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Erro ao obter especificação do asset {asset_id}: {e}")
            return None

    async def get_asset_files(self, group_id: str, asset_id: str, version: str = None) -> Optional[Dict]:
        """Obtém lista de arquivos de um asset (inclui RAML, OAS, etc.)"""
        try:
            headers = await self.get_headers()
            
            if not version:
                asset_details = await self.get_asset_details(group_id, asset_id)
                if asset_details:
                    version = asset_details.get('version', '1.0.0')
                else:
                    version = '1.0.0'
            
            logger.info(f"📁 Buscando arquivos para {group_id}/{asset_id} v{version}")
            
            # Primeiro, tentar obter via detalhes do asset (que já incluem os arquivos)
            asset_details = await self.get_asset_details(group_id, asset_id, version)
            if asset_details and 'files' in asset_details:
                files_data = {
                    'files': asset_details['files'],
                    'source': 'asset_details'
                }
                logger.info(f"📁 Arquivos obtidos via asset_details para {group_id}/{asset_id}")
                return files_data
            
            # Se não funcionou, tentar endpoint específico de arquivos
            url = f"{self.base_url}/exchange/api/v2/assets/{group_id}/{asset_id}/{version}/files"
            
            self._log_curl_command("GET", url, headers)
            
            response = await self.httpx_client.get(url, headers=headers)
            response.raise_for_status()
            
            files_data = response.json()
            files_data['source'] = 'files_endpoint'
            logger.info(f"📁 Arquivos obtidos via endpoint específico para {group_id}/{asset_id}")
            
            return files_data
            
        except Exception as e:
            logger.error(f"❌ Erro ao obter arquivos do asset {asset_id}: {e}")
            return None

    async def get_asset_file_content(self, group_id: str, asset_id: str, version: str, file_path: str) -> Optional[str]:
        """Obtém o conteúdo de um arquivo específico do asset"""
        try:
            headers = await self.get_headers()
            
            url = f"{self.base_url}/exchange/api/v2/assets/{group_id}/{asset_id}/{version}/files/{file_path}"
            
            self._log_curl_command("GET", url, headers)
            
            response = await self.httpx_client.get(url, headers=headers)
            response.raise_for_status()
            
            content = response.text
            logger.info(f"📄 Conteúdo do arquivo {file_path} obtido")
            
            return content
            
        except Exception as e:
            logger.error(f"❌ Erro ao obter conteúdo do arquivo {file_path}: {e}")
            return None

    async def close(self):
        """Fecha o cliente HTTP"""
        await self.httpx_client.aclose()

# Instância global do cliente
mulesoft_client = MuleSoftExchangeClient()

# Servidor MCP
app = Server("mulesoft-exchange-server")

@app.list_resources()
async def list_resources() -> List[Resource]:
    """Lista recursos disponíveis"""
    return [
        Resource(
            uri="mulesoft://apis",
            name="MuleSoft APIs",
            description="Lista de APIs disponíveis no MuleSoft Exchange",
            mimeType="application/json"
        ),
        Resource(
            uri="mulesoft://connectors", 
            name="MuleSoft Connectors",
            description="Lista de conectores disponíveis no MuleSoft Exchange",
            mimeType="application/json"
        )
    ]

@app.read_resource()
async def read_resource(uri: str) -> str:
    """Lê conteúdo de um recurso"""
    if uri == "mulesoft://apis":
        apis = await mulesoft_client.search_assets("", ["rest-api", "soap-api", "http-api"])
        return json.dumps({
            "apis": [
                {
                    "name": api.get("name", ""),
                    "description": api.get("description", ""),
                    "groupId": api.get("groupId", ""),
                    "assetId": api.get("assetId", ""),
                    "type": api.get("type", ""),
                    "version": api.get("version", ""),
                    "tags": [tag.get("value", "") for tag in api.get("tags", [])]
                }
                for api in apis
            ]
        }, indent=2)
    
    elif uri == "mulesoft://connectors":
        connectors = await mulesoft_client.search_assets("", ["connector"])
        return json.dumps({
            "connectors": [
                {
                    "name": connector.get("name", ""),
                    "description": connector.get("description", ""),
                    "groupId": connector.get("groupId", ""),
                    "assetId": connector.get("assetId", ""),
                    "version": connector.get("version", "")
                }
                for connector in connectors
            ]
        }, indent=2)
    
    else:
        raise ValueError(f"Recurso não encontrado: {uri}")

@app.list_tools()
async def list_tools() -> List[Tool]:
    """Lista ferramentas disponíveis"""
    return [
        Tool(
            name="search_apis",
            description="Busca APIs no MuleSoft Exchange por termo de pesquisa ou funcionalidade",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Termo de busca para encontrar APIs (ex: 'payment', 'account', 'cash')"
                    },
                    "api_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tipos de API a buscar (rest-api, soap-api, http-api)",
                        "default": ["rest-api", "soap-api", "http-api"]
                    }
                },
                "required": ["search_term"]
            }
        ),
        Tool(
            name="get_api_details",
            description="Obtém detalhes completos de uma API específica",
            inputSchema={
                "type": "object", 
                "properties": {
                    "group_id": {
                        "type": "string",
                        "description": "ID do grupo da API"
                    },
                    "asset_id": {
                        "type": "string", 
                        "description": "ID do asset da API"
                    }
                },
                "required": ["group_id", "asset_id"]
            }
        ),
        Tool(
            name="find_apis_by_category",
            description="Encontra APIs por categoria ou funcionalidade específica",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Categoria funcional (ex: 'banking', 'payment', 'account', 'customer')"
                    }
                },
                "required": ["category"]
            }
        ),
        Tool(
            name="get_api_specification",
            description="Obtém a especificação OpenAPI/RAML de uma API específica para análise detalhada",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "string",
                        "description": "ID do grupo da API"
                    },
                    "asset_id": {
                        "type": "string",
                        "description": "ID do asset da API"
                    },
                    "version": {
                        "type": "string",
                        "description": "Versão específica da API (opcional, usa mais recente se não informado)"
                    }
                },
                "required": ["group_id", "asset_id"]
            }
        ),
        Tool(
            name="get_api_files",
            description="Lista todos os arquivos de uma API (RAML, OpenAPI, documentação, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "string",
                        "description": "ID do grupo da API"
                    },
                    "asset_id": {
                        "type": "string",
                        "description": "ID do asset da API"
                    },
                    "version": {
                        "type": "string",
                        "description": "Versão específica da API (opcional)"
                    }
                },
                "required": ["group_id", "asset_id"]
            }
        ),
        Tool(
            name="analyze_api_endpoints",
            description="Analisa os endpoints de uma API e fornece informações detalhadas sobre suas operações",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "string",
                        "description": "ID do grupo da API"
                    },
                    "asset_id": {
                        "type": "string",
                        "description": "ID do asset da API"
                    },
                    "version": {
                        "type": "string",
                        "description": "Versão específica da API (opcional)"
                    }
                },
                "required": ["group_id", "asset_id"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Executa uma ferramenta"""
    try:
        logger.info(f"🛠️  Tool called: {name} with arguments: {arguments}")
        
        if name == "search_apis":
            search_term = arguments.get("search_term", "")
            api_types = arguments.get("api_types", ["rest-api", "soap-api", "http-api"])
            
            logger.info(f"🔍 Searching APIs with term: '{search_term}', types: {api_types}")
            
            apis = await mulesoft_client.search_assets(search_term, api_types)
            
            if not apis:
                logger.warning(f"⚠️  No APIs found for term '{search_term}'")
                return [TextContent(
                    type="text",
                    text=f"Nenhuma API encontrada para o termo '{search_term}'"
                )]
            
            # Formata resposta em linguagem natural
            response = f"Encontrei {len(apis)} API(s) relacionada(s) a '{search_term}':\n\n"
            
            for i, api in enumerate(apis[:10], 1):  # Limita a 10 resultados
                name_api = api.get("name", "Nome não disponível")
                description = api.get("description", "Descrição não disponível")
                asset_type = api.get("type", "")
                version = api.get("version", "")
                
                response += f"{i}. **{name_api}** (v{version})\n"
                response += f"   - Tipo: {asset_type}\n"
                response += f"   - Descrição: {description[:200]}{'...' if len(description) > 200 else ''}\n"
                response += f"   - ID: {api.get('groupId')}/{api.get('assetId')}\n\n"
            
            logger.info(f"✅ Search successful: returning {min(len(apis), 10)} results")
            return [TextContent(type="text", text=response)]
        
        elif name == "get_api_details":
            group_id = arguments.get("group_id")
            asset_id = arguments.get("asset_id")
            
            logger.info(f"📋 Getting details for API: {group_id}/{asset_id}")
            
            details = await mulesoft_client.get_asset_details(group_id, asset_id)
            
            if not details:
                logger.warning(f"⚠️  No details found for API {asset_id}")
                return [TextContent(
                    type="text",
                    text=f"Não foi possível obter detalhes da API {asset_id}"
                )]
            
            # Formata detalhes em linguagem natural
            name_api = details.get("name", "")
            description = details.get("description", "")
            version = details.get("version", "")
            api_type = details.get("type", "")
            
            response = f"**Detalhes da API: {name_api}**\n\n"
            response += f"- **Versão**: {version}\n"
            response += f"- **Tipo**: {api_type}\n"
            response += f"- **Descrição**: {description}\n"
            response += f"- **Grupo**: {group_id}\n"
            response += f"- **Asset ID**: {asset_id}\n"
            
            # Adiciona tags se disponível
            tags = details.get("tags", [])
            if tags:
                tag_values = [tag.get("value", "") for tag in tags if tag.get("value")]
                if tag_values:
                    response += f"- **Tags**: {', '.join(tag_values)}\n"
            
            # Adiciona informações de arquivos se disponível
            files = details.get("files", [])
            if files:
                response += f"- **Arquivos disponíveis**: {len(files)}\n"
                for file_info in files[:3]:  # Mostrar só os primeiros 3
                    classifier = file_info.get("classifier", "N/A")
                    packaging = file_info.get("packaging", "N/A")
                    response += f"  - {classifier} ({packaging})\n"
                if len(files) > 3:
                    response += f"  - ... e mais {len(files) - 3} arquivo(s)\n"
            
            logger.info(f"✅ Details retrieved successfully for {asset_id}")
            return [TextContent(type="text", text=response)]
        
        elif name == "get_api_specification":
            group_id = arguments.get("group_id")
            asset_id = arguments.get("asset_id")
            version = arguments.get("version")
            
            logger.info(f"📋 Getting API specification for: {group_id}/{asset_id}")
            
            specification = await mulesoft_client.get_asset_specification(group_id, asset_id, version)
            
            if not specification:
                logger.warning(f"⚠️ No specification found for API {asset_id}")
                return [TextContent(
                    type="text",
                    text=f"Não foi possível obter a especificação da API {asset_id}"
                )]
            
            # Formatar especificação para o agente de IA
            response = f"**Especificação da API: {asset_id}**\n\n"
            
            if isinstance(specification, dict):
                spec_type = specification.get('type', 'unknown')
                classifier = specification.get('classifier', 'unknown')
                
                if spec_type in ['openapi_yaml', 'openapi_json']:
                    # Especificação extraída de ZIP
                    response += f"**Origem:** Arquivo ZIP extraído\n"
                    response += f"**Classificador:** {classifier}\n"
                    response += f"**Tipo:** {spec_type}\n"
                    
                    if 'file_name' in specification:
                        response += f"**Arquivo:** {specification['file_name']}\n"
                    
                    if 'files_in_zip' in specification:
                        files_in_zip = specification['files_in_zip']
                        response += f"**Arquivos no ZIP:** {', '.join(files_in_zip)}\n"
                    
                    content = specification.get('content', '')
                    
                    if spec_type == 'openapi_json' and isinstance(content, dict):
                        # OpenAPI em formato JSON
                        response += "\n**Especificação OpenAPI (JSON):**\n"
                        
                        # Extrair informações principais
                        if 'openapi' in content:
                            response += f"- **Versão OpenAPI:** {content.get('openapi', 'N/A')}\n"
                        elif 'swagger' in content:
                            response += f"- **Versão Swagger:** {content.get('swagger', 'N/A')}\n"
                        
                        if 'info' in content:
                            info = content['info']
                            response += f"- **Título:** {info.get('title', 'N/A')}\n"
                            response += f"- **Versão:** {info.get('version', 'N/A')}\n"
                            response += f"- **Descrição:** {info.get('description', 'N/A')}\n"
                        
                        if 'servers' in content:
                            servers = content['servers']
                            response += f"- **Servidores:** {len(servers)} configurados\n"
                            for i, server in enumerate(servers[:2]):  # Mostrar apenas os primeiros 2
                                response += f"  - {server.get('url', 'N/A')} - {server.get('description', 'N/A')}\n"
                        
                        if 'paths' in content:
                            paths = content['paths']
                            response += f"- **Endpoints:** {len(paths)} definidos\n"
                            
                            # Mostrar alguns endpoints
                            response += "\n**Principais Endpoints:**\n"
                            for i, (path, methods) in enumerate(list(paths.items())[:8]):
                                response += f"- `{path}`: {', '.join(methods.keys())}\n"
                            if len(paths) > 8:
                                response += f"... e mais {len(paths) - 8} endpoints\n"
                        
                        # Mostrar o JSON completo (truncado)
                        response += f"\n**Especificação Completa (JSON):**\n```json\n{json.dumps(content, indent=2)[:3000]}"
                        if len(json.dumps(content)) > 3000:
                            response += "\n... (especificação truncada)"
                        response += "\n```"
                        
                    elif spec_type == 'openapi_yaml':
                        # OpenAPI em formato YAML
                        response += "\n**Especificação OpenAPI (YAML):**\n"
                        response += f"```yaml\n{content[:4000]}"
                        if len(content) > 4000:
                            response += "\n... (especificação truncada)"
                        response += "\n```"
                        
                elif 'content' in specification:
                    # Formato legado ou outros tipos
                    content = specification['content']
                    content_type = specification.get('content_type', 'text/plain')
                    classifier = specification.get('classifier', 'unknown')
                    
                    response += f"**Tipo:** {content_type}\n"
                    response += f"**Classificador:** {classifier}\n"
                    
                    if specification.get('is_zip', False):
                        response += f"**Nota:** {specification.get('note', '')}\n"
                        response += f"**Arquivo principal:** {specification.get('main_file', 'N/A')}\n"
                        response += "**Conteúdo:** Arquivo ZIP - use get_api_files para ver detalhes\n"
                    else:
                        response += f"**Conteúdo da Especificação:**\n\n```\n{content[:3000]}"
                        if len(str(content)) > 3000:
                            response += "\n... (conteúdo truncado - especificação completa muito longa)"
                        response += "\n```"
                    
                else:
                    # É um JSON estruturado direto (APIs tradicionais)
                    if 'swagger' in specification or 'openapi' in specification:
                        # OpenAPI/Swagger direto
                        response += "**Formato:** OpenAPI/Swagger\n"
                        if 'info' in specification:
                            info = specification['info']
                            response += f"**Título:** {info.get('title', 'N/A')}\n"
                            response += f"**Versão:** {info.get('version', 'N/A')}\n"
                            response += f"**Descrição:** {info.get('description', 'N/A')}\n"
                        
                        if 'paths' in specification:
                            paths = specification['paths']
                            response += f"\n**Endpoints ({len(paths)} encontrados):**\n"
                            for path, methods in list(paths.items())[:10]:
                                response += f"- `{path}`: {', '.join(methods.keys())}\n"
                            if len(paths) > 10:
                                response += f"... e mais {len(paths) - 10} endpoints\n"
                                
                    elif '#%RAML' in str(specification):
                        # RAML
                        response += "**Formato:** RAML\n"
                        response += f"**Conteúdo:**\n```yaml\n{str(specification)[:2000]}...\n```"
                    
                    else:
                        # Formato genérico
                        response += f"**Especificação (JSON):**\n```json\n{json.dumps(specification, indent=2)[:2000]}...\n```"
            
            logger.info(f"✅ Specification retrieved successfully for {asset_id}")
            return [TextContent(type="text", text=response)]
        
        elif name == "get_api_files":
            group_id = arguments.get("group_id")
            asset_id = arguments.get("asset_id")
            version = arguments.get("version")
            
            logger.info(f"📁 Getting files for API: {group_id}/{asset_id}")
            
            files = await mulesoft_client.get_asset_files(group_id, asset_id, version)
            
            if not files:
                logger.warning(f"⚠️ No files found for API {asset_id}")
                return [TextContent(
                    type="text",
                    text=f"Não foi possível obter os arquivos da API {asset_id}"
                )]
            
            response = f"**Arquivos da API: {asset_id}**\n\n"
            
            # Extrair lista de arquivos dependendo da estrutura
            file_list = []
            if isinstance(files, dict):
                if 'files' in files:
                    file_list = files['files']
                    source = files.get('source', 'unknown')
                    response += f"**Fonte:** {source}\n"
                elif isinstance(files, list):
                    file_list = files
                else:
                    # Se não tem estrutura reconhecida, mostrar como JSON
                    response += f"**Estrutura de arquivos:**\n```json\n{json.dumps(files, indent=2)[:1000]}...\n```"
                    return [TextContent(type="text", text=response)]
            elif isinstance(files, list):
                file_list = files
            
            if file_list:
                response += f"**Total de arquivos:** {len(file_list)}\n\n"
                
                # Categorizar arquivos por tipo
                specs = []
                docs = []
                examples = []
                others = []
                
                for file_info in file_list:
                    classifier = file_info.get('classifier', 'N/A')
                    packaging = file_info.get('packaging', 'N/A')
                    main_file = file_info.get('mainFile', '')
                    external_link = file_info.get('externalLink', '')
                    created_date = file_info.get('createdDate', '')
                    
                    file_desc = f"{classifier} ({packaging})"
                    if main_file:
                        file_desc += f" - {main_file}"
                    if created_date:
                        try:
                            # Extrair só a data
                            date_part = created_date.split('T')[0]
                            file_desc += f" - {date_part}"
                        except:
                            pass
                    
                    # Categorizar por tipo de arquivo
                    if classifier in ['oas', 'fat-oas', 'raml', 'fat-raml']:
                        specs.append(file_desc)
                    elif 'doc' in classifier.lower() or packaging in ['md', 'html']:
                        docs.append(file_desc)
                    elif 'example' in classifier.lower():
                        examples.append(file_desc)
                    else:
                        others.append(file_desc)
                
                if specs:
                    response += "**📋 Especificações:**\n"
                    for spec in specs:
                        response += f"- {spec}\n"
                    response += "\n"
                
                if docs:
                    response += "**📚 Documentação:**\n"
                    for doc in docs:
                        response += f"- {doc}\n"
                    response += "\n"
                
                if examples:
                    response += "**📝 Exemplos:**\n"
                    for example in examples:
                        response += f"- {example}\n"
                    response += "\n"
                
                if others:
                    response += "**📄 Outros arquivos:**\n"
                    for other in others:
                        response += f"- {other}\n"
            else:
                response += "**Nenhum arquivo encontrado.**\n"
            
            logger.info(f"✅ Files retrieved successfully for {asset_id}")
            return [TextContent(type="text", text=response)]
        
        elif name == "analyze_api_endpoints":
            group_id = arguments.get("group_id")
            asset_id = arguments.get("asset_id")
            version = arguments.get("version")
            
            logger.info(f"🔍 Analyzing endpoints for API: {group_id}/{asset_id}")
            
            # Primeiro, obter a especificação
            specification = await mulesoft_client.get_asset_specification(group_id, asset_id, version)
            
            if not specification:
                return [TextContent(
                    type="text",
                    text=f"Não foi possível obter a especificação da API {asset_id} para análise"
                )]
            
            response = f"**Análise de Endpoints - API: {asset_id}**\n\n"
            
            try:
                # Analisar OpenAPI/Swagger
                spec_content = None
                
                # Extrair conteúdo baseado no tipo de especificação
                if isinstance(specification, dict):
                    spec_type = specification.get('type', 'unknown')
                    
                    if spec_type in ['openapi_yaml', 'openapi_json']:
                        # Especificação extraída de ZIP
                        if spec_type == 'openapi_json':
                            spec_content = specification.get('content', {})
                        else:
                            # Para YAML, tentar fazer parse básico para extrair paths
                            yaml_content = specification.get('content', '')
                            # Implementação básica de extração de paths do YAML
                            # (seria melhor usar uma biblioteca YAML, mas vamos fazer parsing básico)
                            if 'paths:' in yaml_content:
                                response += "**Formato detectado:** OpenAPI YAML\n"
                                response += "**Análise:** Especificação em formato YAML detectada.\n"
                                response += "Para análise completa dos endpoints, veja a especificação YAML acima.\n"
                                return [TextContent(type="text", text=response)]
                    
                    elif 'content' in specification and isinstance(specification['content'], dict):
                        spec_content = specification['content']
                    elif 'paths' in specification:
                        spec_content = specification
                
                if spec_content and isinstance(spec_content, dict) and 'paths' in spec_content:
                    paths = spec_content['paths']
                    
                    response += f"**Total de endpoints:** {len(paths)}\n\n"
                    
                    # Agrupar por método HTTP
                    methods_count = {}
                    endpoint_details = []
                    
                    for path, methods in paths.items():
                        for method, details in methods.items():
                            method_upper = method.upper()
                            methods_count[method_upper] = methods_count.get(method_upper, 0) + 1
                            
                            summary = details.get('summary', 'N/A')
                            description = details.get('description', '')
                            
                            endpoint_details.append({
                                'path': path,
                                'method': method_upper,
                                'summary': summary,
                                'description': description[:100] + '...' if len(description) > 100 else description
                            })
                    
                    # Estatísticas por método
                    response += "**Métodos HTTP:**\n"
                    for method, count in sorted(methods_count.items()):
                        response += f"- {method}: {count} endpoints\n"
                    response += "\n"
                    
                    # Endpoints principais
                    response += "**Principais Endpoints:**\n"
                    for endpoint in endpoint_details[:10]:
                        response += f"- **{endpoint['method']} {endpoint['path']}**\n"
                        response += f"  - {endpoint['summary']}\n"
                        if endpoint['description']:
                            response += f"  - {endpoint['description']}\n"
                        response += "\n"
                    
                    if len(endpoint_details) > 10:
                        response += f"... e mais {len(endpoint_details) - 10} endpoints\n"
                        
                    # Análise de padrões
                    response += "**Padrões identificados:**\n"
                    
                    # Padrões de URL
                    crud_patterns = []
                    for endpoint in endpoint_details:
                        path = endpoint['path']
                        method = endpoint['method']
                        
                        if method == 'GET' and '{id}' in path:
                            crud_patterns.append(f"Consulta individual: {method} {path}")
                        elif method == 'GET' and '{id}' not in path:
                            crud_patterns.append(f"Listagem: {method} {path}")
                        elif method == 'POST':
                            crud_patterns.append(f"Criação: {method} {path}")
                        elif method == 'PUT' or method == 'PATCH':
                            crud_patterns.append(f"Atualização: {method} {path}")
                        elif method == 'DELETE':
                            crud_patterns.append(f"Exclusão: {method} {path}")
                    
                    # Mostrar apenas alguns padrões únicos
                    unique_patterns = list(set(crud_patterns))
                    for pattern in unique_patterns[:5]:
                        response += f"- {pattern}\n"
                
                else:
                    response += "**Análise:** Especificação não está no formato OpenAPI padrão.\n"
                    
                    # Tentar analisar se é RAML ou outro formato
                    if isinstance(specification, dict):
                        spec_type = specification.get('type', 'unknown')
                        classifier = specification.get('classifier', '')
                        
                        if spec_type == 'openapi_yaml':
                            response += "**Formato detectado:** OpenAPI YAML\n"
                            response += "A especificação está em formato YAML. Para análise detalhada, veja o conteúdo YAML na resposta da ferramenta `get_api_specification`.\n"
                        elif 'raml' in classifier.lower():
                            response += "**Formato detectado:** RAML\n"
                            response += "Para análise detalhada de RAML, use a ferramenta `get_api_specification`.\n"
                        else:
                            response += f"**Formato detectado:** {classifier}\n"
                            response += "Para ver a especificação completa, use `get_api_specification`.\n"
                    else:
                        response += "**Formato:** Não foi possível determinar\n"
                        response += "Use `get_api_specification` para investigar a estrutura.\n"
            
            except Exception as e:
                response += f"**Erro na análise:** {str(e)}\n"
                response += "Tente usar `get_api_specification` para ver a especificação completa.\n"
            
            logger.info(f"✅ Endpoint analysis completed for {asset_id}")
            return [TextContent(type="text", text=response)]
        
        elif name == "find_apis_by_category":
            category = arguments.get("category", "").lower()
            
            logger.info(f"🏷️  Finding APIs by category: '{category}'")
            
            # Busca APIs relacionadas à categoria
            apis = await mulesoft_client.search_assets(category, ["rest-api", "soap-api", "http-api"])
            
            if not apis:
                logger.warning(f"⚠️  No APIs found for category '{category}'")
                return [TextContent(
                    type="text",
                    text=f"Nenhuma API encontrada na categoria '{category}'"
                )]
            
            # Filtra APIs mais relevantes para a categoria
            relevant_apis = []
            for api in apis:
                name_api = api.get("name", "").lower()
                description = api.get("description", "").lower()
                tags = [tag.get("value", "").lower() for tag in api.get("tags", [])]
                
                # Verifica se a categoria aparece no nome, descrição ou tags
                if (category in name_api or category in description or 
                    any(category in tag for tag in tags)):
                    relevant_apis.append(api)
            
            if not relevant_apis:
                relevant_apis = apis[:5]  # Usa os primeiros 5 se não houver correspondência exata
            
            response = f"APIs encontradas na categoria '{category}':\n\n"
            
            for i, api in enumerate(relevant_apis[:5], 1):
                name_api = api.get("name", "")
                description = api.get("description", "")
                
                response += f"{i}. **{name_api}**\n"
                response += f"   - {description[:150]}{'...' if len(description) > 150 else ''}\n"
                response += f"   - Para mais detalhes use: {api.get('groupId')}/{api.get('assetId')}\n\n"
            
            logger.info(f"✅ Category search successful: found {len(relevant_apis)} relevant APIs")
            return [TextContent(type="text", text=response)]
        
        else:
            logger.error(f"❌ Unknown tool: {name}")
            return [TextContent(
                type="text",
                text=f"Ferramenta '{name}' não reconhecida"
            )]
            
    except Exception as e:
        logger.error(f"💥 Error executing tool {name}: {e}")
        import traceback
        logger.error(f"💥 Stack trace: {traceback.format_exc()}")
        return [TextContent(
            type="text",
            text=f"Erro ao executar a ferramenta: {str(e)}"
        )]

async def main():
    """Função principal do servidor"""
    try:
        # Testa autenticar na inicialização
        if not await mulesoft_client.authenticate():
            logger.error("Falha na autenticação inicial")
            sys.exit(1)
        
        logger.info("Servidor MCP MuleSoft Exchange iniciado")
        
        # Inicia o servidor stdio
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream, 
                write_stream,
                app.create_initialization_options()
            )
    
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro no servidor: {e}")
    finally:
        await mulesoft_client.close()

if __name__ == "__main__":
    asyncio.run(main())