'''
Collect data in a mongo database.
'''

import datetime

import pymongo

import salt.log

log = salt.log.getLogger(__name__)

__opts__ = {
            'mongo.host': 'salt',
            'mongo.port': 27017,
            'mongo.db': 'salt',
            'mongo.user': '',
            'mongo.password': '',
           }

def collector(hostname, cmd, result):
    '''
    Collect data in a mongo database.
    '''
    conn = pymongo.Connection(
            __opts__['mongo.host'],
            __opts__['mongo.port'],
            )
    db = conn[__opts__['mongo.db']]

    user = __opts__.get('mongo.user')
    password = __opts__.get('mongo.password')
    if user and password:
        db.authenticate(user, password)

    collection = db[hostname]
    back = {}
    if type(result) == type(dict()):
        for key, value in result.iteritems():
            back[key.replace('.', '-')] = value
    else:
        back = result
    log.debug( back )
    collection.insert({
        'utctime' : datetime.datetime.utcnow(),
        'cmd' : cmd,
        'result' : back})
