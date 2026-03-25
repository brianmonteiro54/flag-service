# flag-service (Python)

Este é o serviço de CRUD (Create, Read, Update, Delete) do projeto ToggleMaster. Ele é responsável por gerenciar as *definições* das feature flags.

**IMPORTANTE:** Este serviço é protegido e depende que o `auth-service` esteja rodando. Todas as requisições (exceto `/health`) exigem um header `Authorization: Bearer <sua-chave-api>`.

## Tecnologias
 
| Componente | Tecnologia |
|---|---|
| Linguagem | Python 3.11 |
| Framework | Flask + Gunicorn |
| Banco de Dados | PostgreSQL (RDS) |
| Container | Docker (multi-stage build) |
| Orquestração | Kubernetes (EKS) |
| Registry | Amazon ECR |
| CI/CD | GitHub Actions + ArgoCD (GitOps) |
 
## Endpoints
 
| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Health check do serviço |
| `POST` | `/flags` | Cria uma nova feature flag |
| `GET` | `/flags` | Lista todas as flags |
| `GET` | `/flags/<id>` | Retorna uma flag específica |
| `PUT` | `/flags/<id>` | Atualiza uma flag |
| `DELETE` | `/flags/<id>` | Remove uma flag |
 
## Variáveis de Ambiente
 
| Variável | Descrição |
|---|---|
| `DATABASE_URL` | String de conexão PostgreSQL |
| `AUTH_SERVICE_URL` | URL do Auth Service para validação de API Keys |
 
## Pipeline CI/CD (DevSecOps)
 
O workflow do GitHub Actions executa os seguintes estágios:
 
1. **Build & Unit Test** — Instalação de dependências e execução dos testes com `pytest`
2. **Linter** — Análise estática com `flake8`
3. **Security Scan** — SAST com `bandit` + SCA com `Trivy` (bloqueia vulnerabilidades críticas)
4. **Docker Build & Push** — Build da imagem, scan com Trivy e push para o ECR
5. **GitOps Update** — Atualiza a tag da imagem no repositório `deploy-flag-service`
 
## Deploy (GitOps)
 
O deploy segue o modelo GitOps com ArgoCD. Ao final do pipeline de CI, a tag da imagem é atualizada automaticamente no repositório [`deploy-flag-service`](https://github.com/brianmonteiro54/deploy-flag-service), e o ArgoCD sincroniza a mudança no cluster EKS.
 
## Executando Localmente
 
```bash
# Configurar variáveis
cp .env.example .env
 
# Instalar dependências
pip install -r requirements.txt
 
# Rodar
python app.py
```
 
## Estrutura do Projeto
 
```
├── .github/workflows/ci.yaml   # Pipeline CI/CD
├── db/init.sql                  # Script de inicialização do banco
├── tests/test_app.py            # Testes unitários
├── Dockerfile                   # Build multi-stage (Python)
├── app.py                       # Aplicação Flask
├── requirements.txt             # Dependências Python
└── README.md
```

## 📦 Pré-requisitos (Local)

* [Python](https://www.python.org/) (versão 3.9 ou superior)
* [PostgreSQL](https://www.postgresql.org/download/) (rodando localmente ou em um contêiner Docker)
* O `auth-service` deve estar rodando (localmente na porta `8001`).

## 🚀 Rodando Localmente

1.  **Clone o repositório** e entre na pasta `flag-service`.

2.  **Prepare o Banco de Dados:**
    * Crie um banco de dados no seu PostgreSQL (ex: `flags_db`).
    * Execute o script `db/init.sql` para criar a tabela `flags`:
        ```bash
        psql -U seu_usuario -d flags_db -f db/init.sql
        ```

3.  **Configure as Variáveis de Ambiente:**
    Crie um arquivo chamado `.env` na raiz desta pasta (`flag-service/`) com o seguinte conteúdo:
    ```.env
    # String de conexão do seu banco de dados PostgreSQL
    DATABASE_URL="postgres://SEU_USUARIO:SUA_SENHA@localhost:5432/flags_db"
    
    # Porta que este serviço (flag-service) irá rodar
    PORT="8002"
    
    # URL do auth-service (que deve estar rodando na porta 8001)
    AUTH_SERVICE_URL="http://localhost:8001"
    ```

4.  **Instale as Dependências:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Inicie o Serviço:**
    ```bash
    gunicorn --bind 0.0.0.0:8002 app:app
    ```
    O servidor estará rodando em `http://localhost:8002`.

## 🧪 Testando os Endpoints

**Primeiro, você precisa de uma chave de API válida!**

1.  Vá até o terminal do `auth-service` (que deve estar rodando) e crie uma chave:
    ```bash
    curl -X POST http://localhost:8001/admin/keys \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer admin-secreto-123" \
    -d '{"name": "admin-para-flag-service"}'
    ```
2.  Copie a chave retornada (ex: `tm_key_...`). Vamos chamá-la de `SUA_CHAVE_API` no resto dos exemplos.

---

**Agora, teste o `flag-service`:**

**1. Verifique a Saúde (Health Check):**
```bash
curl http://localhost:8002/health
```

Saída esperada: `{"status":"ok"}`

**2. Tente Acessar um Endpoint Protegido (Sem Chave):**
```bash
curl http://localhost:8002/flags
```

Saída esperada: `{"error":"Authorization header obrigatório"}`

**3. Crie uma nova Flag (Com a Chave Correta):**
```bash
curl -X POST http://localhost:8002/flags \
-H "Content-Type: application/json" \
-H "Authorization: Bearer SUA_CHAVE_API" \
-d '{
    "name": "enable-new-dashboard",
    "description": "Ativa o novo dashboard para usuários",
    "is_enabled": true
}'
```
Saída esperada: (Um JSON com os dados da flag criada).

**4. Liste todas as Flags:**
```bash
curl http://localhost:8002/flags \
-H "Authorization: Bearer SUA_CHAVE_API"
```
Saída esperada: (Uma lista `[]` contendo a flag que você criou).

**5. Desative a Flag (PUT):**
```bash
curl -X PUT http://localhost:8002/flags/enable-new-dashboard \
-H "Content-Type: application/json" \
-H "Authorization: Bearer SUA_CHAVE_API" \
-d '{"is_enabled": false}'
```
Saída esperada: (O JSON da flag atualizada, com `"is_enabled": false`).
