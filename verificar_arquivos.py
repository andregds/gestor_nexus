import os


def listar_estrutura(diretorio_inicial):
    print(f"\n📂 ESTRUTURA DO PROJETO: {os.path.abspath(diretorio_inicial)}\n")

    arquivos_importantes = []

    for root, dirs, files in os.walk(diretorio_inicial):
        # Ignorar pastas de sistema/configuração para não poluir a visão
        dirs[:] = [d for d in dirs if
                   d not in ['.git', '.venv', 'venv', '__pycache__', '.idea', '.vscode', 'node_modules']]

        nivel = root.replace(diretorio_inicial, '').count(os.sep)
        indentacao = ' ' * 4 * nivel
        print(f'{indentacao}📁 {os.path.basename(root)}/')

        sub_indentacao = ' ' * 4 * (nivel + 1)
        for f in files:
            print(f'{sub_indentacao}📄 {f}')
            if f.endswith('.html'):
                arquivos_importantes.append(f)

    print("\n" + "=" * 40)
    print("RESUMO DOS ARQUIVOS HTML ENCONTRADOS:")
    for html in arquivos_importantes:
        print(f" - {html}")
    print("=" * 40 + "\n")


if __name__ == "__main__":
    listar_estrutura(os.getcwd())
    input("Pressione ENTER para fechar...")