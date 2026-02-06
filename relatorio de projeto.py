import os

# ==========================================
# CONFIGURAÇÕES
# ==========================================
OUTPUT_FILE = "projeto_completo_dump.txt"

# Pastas que serão IGNORADAS (para não poluir o log)
IGNORE_DIRS = {
    ".venv", "venv", "env", "__pycache__", ".git", ".idea", ".vscode",
    "node_modules", "build", "dist", "migrations", "instance"
}

# Extensões de arquivos que serão LIDOS
ALLOWED_EXTENSIONS = {
    ".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".ini", ".sql"
}

# Arquivos específicos para ignorar (por segurança ou irrelevância)
IGNORE_FILES = {
    "package-lock.json", "yarn.lock", "poetry.lock",
    ".DS_Store", "Thumbs.db", "scan_project.py", "sql_app.db"
}


def generate_project_dump():
    project_root = os.getcwd()
    print(f"📂 Iniciando varredura em: {project_root}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(f"=== SNAPSHOT DO PROJETO ===\n")
        out.write(f"Raiz: {project_root}\n\n")

        # Caminha por todos os diretórios
        for root, dirs, files in os.walk(project_root):
            # Remove pastas ignoradas da busca
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            for file in files:
                # Verifica se o arquivo deve ser ignorado
                if file in IGNORE_FILES:
                    continue

                # Verifica extensão
                ext = os.path.splitext(file)[1].lower()
                if ext in ALLOWED_EXTENSIONS or file == ".env.example":

                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, project_root)

                    # Cabeçalho visual para separar arquivos
                    out.write("\n" + "=" * 60 + "\n")
                    out.write(f"FILE: {rel_path}\n")
                    out.write("=" * 60 + "\n")

                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            # Oculta chaves de API reais se encontrar um arquivo .env
                            if file == ".env":
                                out.write("# [CONTEÚDO DO .ENV OCULTADO POR SEGURANÇA]\n")
                                out.write("# Certifique-se de que as variáveis existem.\n")
                            else:
                                out.write(content)
                    except Exception as e:
                        out.write(f"[Erro ao ler arquivo: {e}]\n")

    print(f"✅ Concluído! Todo o código foi salvo em: {OUTPUT_FILE}")
    print("👉 Abra esse arquivo, copie tudo e me envie.")


if __name__ == "__main__":
    generate_project_dump()
