"""
Setup dos modulos de acabamento (Estudantes, Provas, Redacoes, Materiais).

Executa, de forma IDEMPOTENTE, tudo o que e necessario no BACKEND para as
features novas funcionarem:

  1. Garante as pastas de storage (materiais e fotos de alunos).
  2. Aplica a migracao da foto do aluno          (students.foto_path).
  3. Aplica a migracao de versionamento/formatos  (materiais.versao, historico_versoes, enum tipo).
  4. Verifica que o backend importa sem erros     (smoke test de app.main).
  5. Confere configuracoes relevantes             (sem exibir segredos).

NAO altera dados existentes. As migracoes checam o schema antes de aplicar,
entao o script pode ser executado mais de uma vez sem problemas.

Uso:
    python setup_modulos_acabamento.py
"""
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PY = sys.executable

_falhas = []
_avisos = []


def _titulo(txt):
    print("\n" + "=" * 64)
    print(txt)
    print("=" * 64)


def garantir_storage():
    _titulo("1/5 - Garantindo pastas de storage")
    dirs = [
        BASE_DIR / "storage" / "materiais",
        BASE_DIR / "storage" / "student_photos",
    ]
    for d in dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  OK   {d}")
        except Exception as e:
            print(f"  ERRO ao criar {d}: {e}")
            _falhas.append(f"criar pasta {d.name}")


def rodar_migracao(nome_arquivo, descricao):
    _titulo(descricao)
    script = BASE_DIR / nome_arquivo
    if not script.exists():
        print(f"  ERRO: script nao encontrado: {script}")
        _falhas.append(descricao + " (script ausente)")
        return
    proc = subprocess.run([PY, str(script)], cwd=str(BASE_DIR))
    if proc.returncode == 0:
        print(f"  -> concluida ({nome_arquivo})")
    else:
        print(f"  -> FALHOU (codigo {proc.returncode}) - veja a saida acima")
        _falhas.append(descricao)


def smoke_import():
    _titulo("4/5 - Verificando se o backend importa sem erros")
    code = "import importlib; importlib.import_module('app.main'); print('IMPORT_OK')"
    try:
        proc = subprocess.run(
            [PY, "-c", code],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        print("  AVISO: o import demorou demais (timeout).")
        print("         Verifique manualmente:  python -c \"import app.main\"")
        _avisos.append("smoke import: timeout")
        return

    if "IMPORT_OK" in (proc.stdout or ""):
        print("  OK   app.main importado sem erros (rotas e modelos carregam).")
    else:
        print("  FALHA ao importar app.main. Ultimas linhas do erro:")
        saida = (proc.stderr or proc.stdout or "").strip().splitlines()
        for linha in saida[-18:]:
            print("    " + linha)
        _falhas.append("import do backend (app.main)")


def checar_config():
    _titulo("5/5 - Conferindo configuracoes (sem exibir valores)")
    try:
        sys.path.insert(0, str(BASE_DIR))
        from app.core.config import settings
    except Exception as e:
        print(f"  AVISO: nao foi possivel ler as configuracoes: {e}")
        _avisos.append("leitura de settings")
        return

    obrigatorias = ["ANTHROPIC_API_KEY"]
    opcionais = ["RESEND_API_KEY", "EMAIL_FROM", "FRONTEND_URL"]

    for nome in obrigatorias:
        definido = bool(getattr(settings, nome, None))
        print(f"  [obrigatoria] {nome}: {'definida' if definido else 'NAO definida'}")
        if not definido:
            _avisos.append(f"{nome} nao definida (geracao por IA nao vai funcionar)")

    for nome in opcionais:
        definido = bool(getattr(settings, nome, None))
        print(f"  [opcional]    {nome}: {'definida' if definido else 'nao definida'}")
        if not definido:
            _avisos.append(f"{nome} nao definida (recuperacao de senha por email)")

    # Pagamento (Asaas) - opcional; necessario apenas para cobranca real
    asaas_def = bool(getattr(settings, "ASAAS_API_KEY", None))
    print(f"  [opcional]    ASAAS_API_KEY: {'definida' if asaas_def else 'nao definida'}")
    if asaas_def:
        print(f"                ASAAS_ENV: {getattr(settings, 'ASAAS_ENV', 'sandbox')}")
        if not bool(getattr(settings, 'ASAAS_WEBHOOK_TOKEN', None)):
            _avisos.append("ASAAS_WEBHOOK_TOKEN nao definido (webhook sem validacao de token)")
    else:
        _avisos.append("ASAAS_API_KEY nao definida (checkout cria trial mas nao gera cobranca)")


def resumo():
    _titulo("RESUMO")
    if not _falhas:
        print("OK - Todas as etapas obrigatorias foram concluidas.")
    else:
        print("ATENCAO - etapas que falharam:")
        for f in _falhas:
            print(f"  - {f}")

    if _avisos:
        print("\nAvisos (nao bloqueiam o uso, mas confira):")
        for a in _avisos:
            print(f"  - {a}")

    print("\nPendente (fora do escopo deste script):")
    print("  - Testar em runtime: geracao por IA, limites de plano, uploads (foto/CSV), anti-abuso.")
    print("  - Construir as telas de frontend das features novas (este script cuida so do backend).")
    print("  - (Opcional) Recuperacao de senha: definir RESEND_API_KEY / EMAIL_FROM / FRONTEND_URL no .env.")
    print("  - (Opcional) Pagamento Asaas: definir ASAAS_API_KEY / ASAAS_ENV / ASAAS_WEBHOOK_TOKEN no .env e")
    print("    cadastrar o webhook no painel Asaas apontando para <backend>/api/v1/checkout/webhook/asaas.")
    print("  - (Opcional/limpeza) Remover arquivos orfaos do PEI: pei_novo_endpoint.py, novo_endpoint_pei.txt,")
    print("    e o componente SeletorRelatoriosParaPEI.jsx (nao afetam o funcionamento).")

    print("\nProximo passo: reinicie o backend.")
    print("=" * 64)


def main():
    _titulo("SETUP - Modulos de acabamento (Estudantes / Provas / Redacoes / Materiais)")
    print("Pasta do backend:", BASE_DIR)
    print("Python:", PY)

    garantir_storage()
    rodar_migracao(
        "aplicar_migracao_foto_aluno.py",
        "2/5 - Migracao: foto do aluno (students.foto_path)",
    )
    rodar_migracao(
        "aplicar_migracao_materiais_versao.py",
        "3/5 - Migracao: versionamento e novos formatos de materiais",
    )
    rodar_migracao(
        "aplicar_migracao_revoked_tokens.py",
        "3.1/5 - Migracao: tokens revogados (logout server-side)",
    )
    smoke_import()
    checar_config()
    resumo()

    sys.exit(1 if _falhas else 0)


if __name__ == "__main__":
    main()
