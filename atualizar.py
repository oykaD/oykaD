"""Atualiza a tabela de projetos do README do perfil e cria uma release nova.

Como usar (de qualquer pasta):
    python atualizar.py          -> atualiza, faz commit, tag, push e release
    python atualizar.py --teste  -> só mostra o que mudaria, sem enviar nada

Lê a última versão (tag) de cada programa em programas.json, nas pastas do PC.
Versões do perfil: v0.1.0 ... v0.1.9, v0.2.0 ... v0.9.9, v1.0.0 ... (sem fim).
"""
import json
import os
import re
import subprocess
import sys

# A tela do Windows nem sempre aceita "→"; assim o script não trava ao mostrar.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(os.path.expanduser("~"), "Documents")
GH = r"C:\Program Files\GitHub CLI\gh.exe"
INICIO = "<!-- programas:inicio -->"
FIM = "<!-- programas:fim -->"
ASSINATURA = "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def git(*args, pasta=AQUI, env=None):
    r = subprocess.run(["git", "-C", pasta, *args], capture_output=True, text=True,
                       encoding="utf-8", env=env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def programas():
    with open(os.path.join(AQUI, "programas.json"), encoding="utf-8") as f:
        return json.load(f)


def versao_seguinte(tag):
    """v0.1.9 -> v0.2.0, v0.9.9 -> v1.0.0, v1.2.3 -> v1.2.4."""
    a, b, c = (int(x) for x in tag.lstrip("v").split("."))
    c += 1
    if c > 9:
        c, b = 0, b + 1
    if b > 9:
        b, a = 0, a + 1
    return f"v{a}.{b}.{c}"


def ultima_tag_perfil():
    tags = git("tag", "--list", "v*.*.*", "--sort=-v:refname").splitlines()
    return tags[0] if tags else None


def ultima_versao(p):
    """Última tag do programa, ou 'planning' se ainda não tem nenhuma."""
    pasta = os.path.join(DOCS, p["pasta"])
    prefixo = p.get("prefixo", "")
    try:
        git("fetch", "-q", "--tags", pasta=pasta)
    except RuntimeError:
        pass
    tags = git("tag", "--list", prefixo + "v*", "--sort=-v:refname", pasta=pasta).splitlines()
    return tags[0][len(prefixo):] if tags else "planning"


def tabela(estado):
    linhas = ["| Project | What it does | Version |", "| --- | --- | --- |"]
    for p in programas():
        v = estado.get(p["nome"])
        if v is None:
            continue
        mostra = "planning" if v == "planning" else f"`{v}`"
        linhas.append(f"| **{p['nome']}** | {p['descricao']} | {mostra} |")
    return "\n".join(linhas)


def montar_readme(modelo, estado):
    antes, resto = modelo.split(INICIO)
    _, depois = resto.split(FIM)
    return f"{antes}{INICIO}\n{tabela(estado)}\n{FIM}{depois}"


def mudancas(antigo, novo):
    itens = []
    for p in programas():
        n, a = p["nome"], antigo.get(p["nome"])
        v = novo.get(n)
        if v is None or v == a:
            continue
        if a is None:
            itens.append((n, None, v))
        else:
            itens.append((n, a, v))
    return itens


def textos(itens):
    """Título curto e lista de mudanças em português."""
    def fmt(v):
        return "em planejamento" if v == "planning" else v
    linhas = []
    for n, a, v in itens:
        if a is None:
            linhas.append(f"- Novo: **{n}** ({fmt(v)})")
        else:
            linhas.append(f"- **{n}**: {fmt(a)} → {fmt(v)}")
    if len(itens) == 1:
        n, a, v = itens[0]
        titulo = f"novo {n}" if a is None else f"{n} {fmt(v)}"
    else:
        titulo = f"{len(itens)} programas atualizados"
    return titulo, "\n".join(linhas)


def main():
    teste = "--teste" in sys.argv
    caminho_readme = os.path.join(AQUI, "README.md")
    caminho_estado = os.path.join(AQUI, "versoes.json")
    with open(caminho_readme, encoding="utf-8") as f:
        modelo = f.read()
    with open(caminho_estado, encoding="utf-8") as f:
        antigo = json.load(f)

    novo = {p["nome"]: ultima_versao(p) for p in programas()}
    itens = mudancas(antigo, novo)
    if not itens:
        print("Nada mudou: o perfil já está com as versões mais novas.")
        return

    tag = versao_seguinte(ultima_tag_perfil() or "v0.0.9")
    titulo, corpo = textos(itens)
    print(f"{tag}: {titulo}\n{corpo}")
    if teste:
        return

    git("pull", "-q", "--ff-only")
    with open(caminho_readme, "w", encoding="utf-8", newline="\n") as f:
        f.write(montar_readme(modelo, novo))
    with open(caminho_estado, "w", encoding="utf-8", newline="\n") as f:
        json.dump(novo, f, ensure_ascii=False, indent=2)
        f.write("\n")
    git("add", "README.md", "versoes.json", "programas.json")
    git("commit", "-q", "-m", f"Perfil {tag}: {titulo}\n\n{corpo}{ASSINATURA}")
    git("tag", "-a", tag, "-m", f"{tag}: {titulo}")
    git("push", "-q")
    git("push", "-q", "origin", tag)
    subprocess.run([GH, "release", "create", tag, "-R", "oykaD/oykaD",
                    "--title", f"{tag}: {titulo}", "--notes", corpo], check=True)
    print(f"Pronto: {tag} enviada.")


if __name__ == "__main__":
    main()
