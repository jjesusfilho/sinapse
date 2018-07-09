import json
import requests

from copy import deepcopy
from datetime import datetime
from functools import wraps

from decouple import config
from flask import (
    jsonify,
    request,
    render_template,
    session,
)

from sinapse.buildup import (
    app,
    _LOG_MONGO,
    _ENDERECO_NEO4J,
    _AUTH,
    _HEADERS,
    _AUTH_MPRJ,
)


def respostajson(response):
    usuario = session.get('usuario', "dummy")
    sessionid = request.cookies.get('session')
    _log_response(usuario, sessionid, response)
    dados = response.json()
    if resposta_sensivel(dados):
        return jsonify(remove_info_sensiveis(dados))

    return jsonify(response.json())


def limpa_nos(nos):
    copia_nos = deepcopy(nos)
    for no in copia_nos:
        if 'sensivel' in no['properties'].keys():
            no['labels'] = ['sigiloso']
            no['properties'] = dict()

    return copia_nos


def limpa_linhas(linhas):
    copia_linhas = deepcopy(linhas)
    novas_linhas = []
    for linha in copia_linhas:
        if isinstance(linha, list):
            novas_linhas.append(limpa_linhas(linha))
        elif isinstance(linha, dict):
            if 'sensivel' in linha.keys():
                novas_linhas.append(dict())
            else:
                novas_linhas.append(linha)

    return novas_linhas


def limpa_relacoes(relacoes):
    copia_relacoes = deepcopy(relacoes)
    for relacao in copia_relacoes:
        if 'sensivel' in relacao['properties'].keys():
            relacao['type'] = 'sigiloso'
            relacao['properties'] = dict()

    return copia_relacoes


def remove_info_sensiveis(resposta):
    resp = deepcopy(resposta)
    for data in resp['results'][0]['data']:
        data['graph']['nodes'] = limpa_nos(data['graph']['nodes'])
        data['row'] = limpa_linhas(data['row'])
        data['graph']['relationships'] = limpa_relacoes(
            data['graph']['relationships'])

    return resp


def resposta_sensivel(resposta):
    def parser_dicionario(dicionario, chave):
        if isinstance(dicionario, dict):
            for k, v in dicionario.items():
                if k == chave:
                    yield v
                else:
                    yield from parser_dicionario(v, chave)
        elif isinstance(dicionario, list):
            for item in dicionario:
                yield from parser_dicionario(item, chave)

    try:
        return next(parser_dicionario(resposta, 'sensivel'))
    except StopIteration:
        return False


def _log_response(usuario, sessionid, response):
    _LOG_MONGO.insert(
        {
            'usuario': usuario,
            'datahora': datetime.now(),
            'sessionid': sessionid,
            'resposta': response.json()
        }
    )


def _autenticar(usuario, senha):
    "Autentica o usuário no SCA"
    sessao = requests.session()
    response = sessao.post(
        url=_AUTH_MPRJ,
        data={
            'username': usuario,
            'password': senha
        })
    if response.status_code == 200:
        # TODO: implementar a restrição por grupo do SCA
        # response = sessao.get(url=_USERINFO_MPRJ)
        # json.loads(response.content.decode('utf-8'))
        return usuario
    return None


def login_necessario(funcao):
    @wraps(funcao)
    def funcao_decorada(*args, **kwargs):
        if "usuario" not in session and not config('DEV'):
            return "Não autorizado", 403
        return funcao(*args, **kwargs)
    return funcao_decorada


@app.route("/login", methods=["POST"])
def login():
    usuario = request.form.get("usuario")
    senha = request.form.get("senha")

    resposta = _autenticar(usuario, senha)
    if resposta:
        session['usuario'] = resposta
        return "OK", 201

    return "NOK", 401


@app.route("/logout", methods=["GET", "POST"])
def logout():
    if 'usuario' in session:
        del session['usuario']
        return "OK", 201

    return "Usuário não logado", 200


@app.route("/")
def raiz():
    return render_template('index.html')


@app.route("/api/node")
@login_necessario
def api_node():
    node_id = request.args.get('node_id')

    query = {"statements": [{
        "statement": "MATCH  (n) where id(n) = " + node_id + " return n",
        "resultDataContents": ["row", "graph"]
    }]}

    response = requests.post(
        _ENDERECO_NEO4J % '/db/data/transaction/commit',
        data=json.dumps(query),
        auth=_AUTH,
        headers=_HEADERS)

    return respostajson(response)


@app.route("/api/findNodes")
@login_necessario
def api_findNodes():
    label = request.args.get('label')
    prop = request.args.get('prop')
    val = request.args.get('val')
    # TODO: alterar para prepared statement
    query = {"statements": [{
        "statement": "MATCH (n: %s { %s:toUpper('%s')})"
        " return n" % (label, prop, val),
        "resultDataContents": ["row", "graph"]
    }]}
    response = requests.post(
        _ENDERECO_NEO4J % '/db/data/transaction/commit',
        data=json.dumps(query),
        auth=_AUTH,
        headers=_HEADERS)
    return respostajson(response)


@app.route("/api/nextNodes")
@login_necessario
def api_nextNodes():
    node_id = request.args.get('node_id')
    query = {"statements": [{
        "statement": "MATCH r = (n)-[*..1]-(x) where id(n) = %s"
        " return r,n,x" % node_id,
        "resultDataContents": ["row", "graph"]
    }]}
    response = requests.post(
        _ENDERECO_NEO4J % '/db/data/transaction/commit',
        data=json.dumps(query),
        auth=_AUTH,
        headers=_HEADERS)
    return respostajson(response)


@app.route("/api/nodeProperties")
@login_necessario
def api_nodeProperties():
    label = request.args.get('label')

    cypher = "MATCH (n:" + label + ")  RETURN  keys(n) limit 1"
    query = {"query": cypher}
    response = requests.post(
        _ENDERECO_NEO4J % '/db/data/cypher',
        data=json.dumps(query),
        auth=_AUTH,
        headers=_HEADERS)
    return respostajson(response)


@app.route("/api/labels")
@login_necessario
def api_labels():
    response = requests.get(
        _ENDERECO_NEO4J % '/db/data/labels',
        auth=_AUTH,
        headers=_HEADERS)
    return respostajson(response)


@app.route("/api/relationships")
@login_necessario
def api_relationships():
    response = requests.get(
        _ENDERECO_NEO4J % '/db/data/relationship/types',
        auth=_AUTH,
        headers=_HEADERS)
    return respostajson(response)
