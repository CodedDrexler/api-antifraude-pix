@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

set "TEST_PROJECT=bootcamp-tests-%RANDOM%-%RANDOM%"
set "DATABASE_URL=postgresql+psycopg2://pix:pix@db:5432/pix"
set "INTERNAL_TOKEN=local_test_token"
set "API_PORT=0"
set "GNN_MODE=shadow"
set "EXIT_CODE=1"

echo Verificando Docker Desktop...
docker info >nul 2>&1
if errorlevel 1 (
    echo ERRO: abra o Docker Desktop e tente novamente.
    goto finish
)
docker compose version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Docker Compose nao esta disponivel.
    goto finish
)

echo.
echo [1/5] Preparando API e banco de testes isolados...
call :compose up --build --wait --wait-timeout 120 api
if errorlevel 1 goto cleanup

echo.
echo [2/5] Construindo o container de testes...
call :compose --profile test build tests
if errorlevel 1 goto cleanup

echo.
echo [3/5] Executando os testes automatizados...
call :compose --profile test run --rm --no-deps tests pytest -q
if errorlevel 1 goto cleanup

echo.
echo [4/5] Verificando imports e qualidade do codigo...
call :compose --profile test run --rm --no-deps tests ruff check src tests scripts
if errorlevel 1 goto cleanup

echo.
echo [5/5] Verificando formatacao...
call :compose --profile test run --rm --no-deps tests ruff format --check src tests scripts
if errorlevel 1 goto cleanup
set "EXIT_CODE=0"

:cleanup
if not "%EXIT_CODE%"=="0" call :compose logs --tail=60
echo.
echo Removendo apenas os containers e o banco desta execucao de testes...
call :compose down --volumes --remove-orphans
if errorlevel 1 (
    echo ERRO: nao foi possivel concluir a limpeza do ambiente de testes.
    set "EXIT_CODE=1"
)

:finish
echo.
if "%EXIT_CODE%"=="0" (
    echo SUCESSO: testes, lint e formatacao passaram.
) else (
    echo FALHA: confira as mensagens acima.
)
popd
if /I not "%~1"=="--no-pause" pause
exit /b %EXIT_CODE%

:compose
docker compose -f "%~dp0docker-compose.yml" -p "%TEST_PROJECT%" %*
exit /b %ERRORLEVEL%
