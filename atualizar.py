"""Atualiza a tabela de projetos do README do perfil e cria uma release nova.

Como usar (de qualquer pasta):
    python atualizar.py          -> atualiza, faz commit, tag, push e release
    python atualizar.py --teste  -> só mostra o que mudaria, sem enviar nada

Lê a última versão (tag) de cada programa em programas.json, nas pastas do PC.
Versões do perfil: v0.1.0 ... v0.9.9, v1.0.0 ... v1.0.999, v1.1.0 ... v1.1.999, v1.2.0 ... (igual na v2, v3...).
"""
import json
import os
import re
import subprocess
import sys
import time

# A tela do Windows nem sempre aceita "→"; assim o script não trava ao mostrar.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = os.path.dirname(os.path.abspath(__file__))
DOCS = r"C:\Claude"  # pasta dos projetos (desde 09/11/2026)
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


CAMPOS = ("nome", "descricao")
TRAVA = ".atualizar.lock"
ESPERA_TRAVA = 120  # segundos esperando outra conversa terminar
TRAVA_VELHA = 600   # trava mais velha que isso é de uma execução que travou


def programas():
    with open(os.path.join(AQUI, "programas.json"), encoding="utf-8") as f:
        lista = json.load(f)
    vistos = set()
    for i, p in enumerate(lista, 1):
        faltam = [c for c in CAMPOS if not p.get(c)]
        if faltam:
            raise ValueError(f"programas.json, linha {i} ({p.get('nome', 'sem nome')}): falta {', '.join(faltam)}")
        if p["nome"] in vistos:
            raise ValueError(f"programas.json: {p['nome']} aparece duas vezes")
        vistos.add(p["nome"])
    return lista


class Trava:
    """Impede duas conversas de rodar o script ao mesmo tempo (mesma tag, push recusado)."""

    def __init__(self):
        self.caminho = os.path.join(AQUI, TRAVA)

    def __enter__(self):
        limite = time.time() + ESPERA_TRAVA
        while True:
            try:
                fd = os.open(self.caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.caminho) > TRAVA_VELHA:
                        os.remove(self.caminho)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > limite:
                    raise RuntimeError("Outra conversa está atualizando o perfil agora. "
                                       "Rode de novo daqui a pouco.")
                time.sleep(min(1.0, ESPERA_TRAVA / 10))

    def __exit__(self, *_):
        try:
            os.remove(self.caminho)
        except FileNotFoundError:
            pass


def versao_seguinte(tag):
    """v0.1.9 -> v0.2.0, v0.9.9 -> v1.0.0; da v1 em diante: v1.0.999 -> v1.1.0, v1.9.999 -> v2.0.0."""
    a, b, c = (int(x) for x in tag.lstrip("v").split("."))
    limite = 9 if a == 0 else 999
    c += 1
    if c > limite:
        c, b = 0, b + 1
    if b > 9:
        b, a = 0, a + 1
    return f"v{a}.{b}.{c}"


def ultima_tag_perfil():
    tags = git("tag", "--list", "v*.*.*", "--sort=-v:refname").splitlines()
    return tags[0] if tags else None


def ultima_versao(p, antigo):
    """Última tag do programa, ou 'planning' se ainda não tem nenhuma.
    Sem pasta no PC (projeto que ainda vai começar): 'in development'.
    Se a pasta sumiu (mudou de lugar) e o programa já tinha versão, mantém a versão
    antiga e avisa, em vez de rebaixar o programa no perfil."""
    if not p.get("pasta") or not os.path.isdir(os.path.join(DOCS, p["pasta"])):
        anterior = antigo.get(p["nome"])
        if anterior and anterior.startswith("v"):
            print(f"Aviso: pasta de {p['nome']} não encontrada ({p.get('pasta')}); mantendo {anterior}.")
            return anterior
        return "in development"
    return ultima_versao_da_pasta(p)


def ultima_versao_da_pasta(p):
    pasta = os.path.join(DOCS, p["pasta"])
    prefixo = p.get("prefixo", "")
    try:
        git("fetch", "-q", "--tags", pasta=pasta)
    except RuntimeError:
        pass
    tags = git("tag", "--list", prefixo + "v*", "--sort=-v:refname", pasta=pasta).splitlines()
    return tags[0][len(prefixo):] if tags else "planning"


def tabela(estado):
    """Programas em cima; depois os MCPs ("tipo": "mcp"), os plugins ("tipo": "plugin"), as extensões do Chrome ("tipo": "extensao") e os bots do Discord ("tipo": "bot")."""
    def montar(cabecalho, lista):
        linhas = [f"| {cabecalho} | What it does | Version |", "| --- | --- | --- |"]
        for p in lista:
            v = estado.get(p["nome"])
            if v is None:
                continue
            mostra = v if not v.startswith("v") else f"`{v}`"
            linhas.append(f"| **{p['nome']}** | {p['descricao']} | {mostra} |")
        return linhas

    todos = programas()
    apps = [p for p in todos if p.get("tipo") not in ("extensao", "mcp", "plugin", "bot")]
    mcps = [p for p in todos if p.get("tipo") == "mcp"]
    plugins = [p for p in todos if p.get("tipo") == "plugin"]
    extensoes = [p for p in todos if p.get("tipo") == "extensao"]
    bots = [p for p in todos if p.get("tipo") == "bot"]
    linhas = montar("Project", apps)
    if mcps:
        linhas += ["", "#### MCP servers", "",
                   "<sub>Bridges that let Claude work inside my Adobe apps, the way I edit.</sub>", ""] + montar("MCP", mcps)
    if plugins:
        linhas += ["", "#### Plugins", ""] + montar("Plugin", plugins)
    if extensoes:
        linhas += ["", "#### Chrome extensions", ""] + montar("Extension", extensoes)
    if bots:
        linhas += ["", "#### Discord bots", ""] + montar("Bot", bots)
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
        return {"planning": "em planejamento", "in development": "em criação"}.get(v, v)
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


def criar_release(tag, titulo, corpo):
    subprocess.run([GH, "release", "create", tag, "-R", "oykaD/oykaD",
                    "--title", f"{tag}: {titulo}", "--notes", corpo], check=True)


def release_pendente(teste):
    """Se a última tag do perfil ficou sem release (o gh falhou depois do push), cria agora."""
    tag = ultima_tag_perfil()
    if not tag:
        return
    r = subprocess.run([GH, "release", "view", tag, "-R", "oykaD/oykaD"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return
    msg = git("log", "-1", "--format=%B", f"{tag}^{{commit}}")
    msg = msg.replace(ASSINATURA.strip(), "").strip()
    primeira, _, corpo = msg.partition("\n")
    titulo = primeira.split(": ", 1)[-1]
    print(f"A release {tag} tinha ficado faltando" + (" (modo teste: não criei)." if teste else "; criando agora."))
    if not teste:
        criar_release(tag, titulo, corpo.strip())


def main():
    teste = "--teste" in sys.argv
    with Trava():
        atualizar(teste)


def atualizar(teste):
    caminho_readme = os.path.join(AQUI, "README.md")
    caminho_estado = os.path.join(AQUI, "versoes.json")
    programas()  # confere o programas.json antes de mexer em qualquer coisa

    # Puxa primeiro e só depois lê o README, o versoes.json e as tags: assim não
    # apaga o que outra conversa enviou nem repete o número de uma tag que já existe.
    if not teste:
        git("pull", "-q", "--ff-only")
        git("fetch", "-q", "--tags")
    lista = programas()
    with open(caminho_readme, encoding="utf-8") as f:
        modelo = f.read()
    with open(caminho_estado, encoding="utf-8") as f:
        antigo = json.load(f)

    release_pendente(teste)

    novo = {p["nome"]: ultima_versao(p, antigo) for p in lista}
    itens = mudancas(antigo, novo)
    if not itens:
        print("Nada mudou: o perfil já está com as versões mais novas.")
        return

    tag = versao_seguinte(ultima_tag_perfil() or "v0.0.9")
    titulo, corpo = textos(itens)
    print(f"{tag}: {titulo}\n{corpo}")
    if teste:
        return

    with open(caminho_readme, "w", encoding="utf-8", newline="\n") as f:
        f.write(montar_readme(modelo, novo))
    with open(caminho_estado, "w", encoding="utf-8", newline="\n") as f:
        json.dump(novo, f, ensure_ascii=False, indent=2)
        f.write("\n")
    git("add", "README.md", "versoes.json", "programas.json")
    git("commit", "-q", "-m", f"Perfil {tag}: {titulo}\n\n{corpo}{ASSINATURA}")
    git("tag", "-a", tag, "-m", f"{tag}: {titulo}")
    try:
        # Commit e tag vão juntos: ou os dois chegam ao GitHub, ou nenhum.
        git("push", "-q", "--atomic", "origin", "HEAD", tag)
    except RuntimeError:
        # Recusado (alguém enviou antes): desfaz o commit e a tag locais para a
        # próxima execução começar limpa, sem tag órfã nem commit preso.
        git("tag", "-d", tag)
        git("reset", "-q", "--keep", "HEAD~1")
        raise RuntimeError(f"O GitHub recusou o envio da {tag} (chegou algo novo antes). "
                           "Nada foi publicado; rode o script de novo.")
    criar_release(tag, titulo, corpo)
    print(f"Pronto: {tag} enviada.")


if __name__ == "__main__":
    main()
