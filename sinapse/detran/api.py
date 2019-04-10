from flask import request, jsonify

from sinapse.buildup import app, _FOTOS_DETRAN
from sinapse.start import login_necessario


@app.route('/api/foto', methods=['GET'])
@login_necessario
def api_photo():
    node_id = request.args.get('node_id')
    rg = request.args.get('rg')

    if node_id is not None:
        photo_doc = _FOTOS_DETRAN.find_one({'node_id': node_id}, {'_id': 0})
    elif rg is not None:
        photo_doc = _FOTOS_DETRAN.find_one({'rg': rg}, {'_id': 0})

    if photo_doc:
        return jsonify(photo_doc)

    return jsonify({})
