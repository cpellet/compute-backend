#!flask/bin/python
from flask import Flask, jsonify, make_response, abort, request, url_for, Markup, render_template
from flask_httpauth import HTTPBasicAuth
from configparser import ConfigParser
import redis
import json

config = ConfigParser()
config.read('config.ini')

auth = HTTPBasicAuth()
r = redis.Redis(host=config.get('Redis', 'host'), port=config.get('Redis', 'port'), db=config.get('Redis', 'db'))

app = Flask(__name__, static_url_path="")

def make_public_score(score, task, shard):
    new_score = {}
    for field in score:
        if field == 'id':
            new_score['uri'] = url_for('get_score', score_id=score['id'], task=task, shard=shard, _external=True)
        else:
            new_score[field] = score[field]
    return new_score

@auth.get_password
def get_password(username):
    if config.get('User', "username"):
        return config.get('User', 'password')
    return None

@auth.error_handler
def unauthorized():
    return make_response(jsonify({'error': 'Unauthorized access'}), 401)

@app.route('/compute/api/scores/<string:task>/<string:shard>', methods=['GET'])
def get_scores(task, shard):
    return jsonify({'scores' : [make_public_score(score, task, shard) for score in json.loads(r.get(task+'/'+shard))]}) if r.get(task+'/'+shard) is not None else make_response(jsonify({'error': task+'/'+shard+' wansn\'t created yet'}), 404)

@app.route('/compute/api/scores/tasks', methods=['GET'])
def get_tasks():
    tasks = []
    for el in r.keys():
        if el.decode('utf8').split('/')[0] not in tasks:
            tasks.append(el.decode('utf8').split('/')[0])
    return jsonify({'tasks' : [task for task in tasks]})

@app.route('/compute/api/scores/<string:task>/shards', methods=['GET'])
def get_shards(task):
    shards = []
    for el in r.keys("*" + task + "*"):
            shards.append(el.decode('utf8').split('/')[1])
    return jsonify({'shards' : [shard for shard in shards]})

@app.route('/compute/api/scores/<string:task>/<string:shard>/<int:score_id>', methods=['GET'])
def get_score(task, shard, score_id):
    if r.get(task+'/'+shard) is None:
        return make_response(jsonify({'error': task+'/'+shard+' wansn\'t created yet'}), 404)
    score = [make_public_score(score, task, shard) for score in json.loads(r.get(task+'/'+shard)) if score['id'] == score_id]
    if len(score) == 0:
        return make_response(jsonify({'error': 'score ' + score_id + ' for ' + task+'/'+shard+' doesn\'t exist'}), 404)
    else:
        return jsonify({'score' : score[0]})

@app.route('/compute/api/scores/<string:task>/<string:shard>/<int:score_id>', methods=['DELETE'])
def delete_score(task, shard, score_id):
    if r.get(task+'/'+shard) is None:
        return make_response(jsonify({'error': task+'/'+shard+' wansn\'t created yet'}), 404)
    score = [score for score in json.loads(r.get(task+'/'+shard)) if score['id'] == score_id]
    if len(score) == 0:
        return make_response(jsonify({'error': 'score ' + score_id + ' for ' + task+'/'+shard+' doesn\'t exist'}), 404)
    new = json.loads(r.get(task+'/'+shard))
    del new[score_id]
    r.set(task+'/'+shard, json.dumps(new))
    r.save()
    return jsonify({'result' : True})

@app.route('/compute/api/scores/<string:task>/<string:shard>', methods=['POST'])
@auth.login_required
def create_score(task, shard):
    if not request.json or not 'score' in request.json:
        abort(400)
    score = {
        'id': json.loads(r.get(task+'/'+shard))[-1]['id'] + 1 if (r.get(task+'/'+shard) is not None) else 0,
        'user': auth.username(),
        'score': request.json.get('score'),
        'edge': request.json.get('edge'),
        'edge_type': request.json.get('edge_type'),
        'description': request.json.get('description'),
        'language': request.json.get('language'),
        'time': request.json.get('time')
    }
    if r.get(task+'/'+shard) is None:
        scores = [score]
        r.set(task+'/'+shard, json.dumps(scores))
    else:
        new = json.loads(r.get(task+'/'+shard))
        new.append(score)
        r.set(task+'/'+shard, json.dumps(new))
    r.save()
    return jsonify({'score': score}), 201

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

#DASHBOARD

@app.route('/dash/scores/<string:task>/<string:shard>')
def scores_chart(task, shard):
    if r.get(task+'/'+shard) is None:
        return render_template('404.html', title=task+'/'+shard)
    ids = []
    scores = []
    shards = []
    timestamps = []
    for el in r.keys():
            shards.append(el.decode('utf8'))
    for score in json.loads(r.get(task+'/'+shard)):
        ids.append(score['id'])
        scores.append(score['score'])
        timestamps.append(score['time'])
    return render_template('scores.html', title=task+'/'+shard, min=min(scores), max=max(scores), ids=ids, scores=scores, shards=shards, timestamps=timestamps, ndata=json.loads(r.get(task+'/'+shard)))

if __name__ == '__main__':
    app.run(debug=True)