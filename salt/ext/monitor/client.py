'''
Create Clients to communicate with the salt-alert daemon

Use:
    import salt.ext.monitor.client
    aclient = salt.ext.monitor.client.AlertClient(opts)
    aclient.alert(<alert data>)
'''
# Import salt modules
import salt.crypt
# Import zeromq libs
import zmq

class AlertClient(object):
    '''
    Connect to the salt-alert daemon
    '''
    def __init__(self, opts):
        self.opts = opts
        self.auth = salt.crypt.SAuth(opts)
        self.socket = self.__get_socket()

    def __get_socket(self):
        '''
        Return a zeromq socket
        '''
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(self.opts['master_uri'])
        return socket

    def alert(self, host, severity, category, msg):
        '''
        Send an alert message to the alert daemon
        '''
        load = {'cmd': '_alert',
                'host': host,
                'severity': severity.lower(),
                'SEVERITY': severity.upper(),
                'category': category,
                'msg': msg}
        payload = {'enc': 'aes',
                   'load': self.auth.crypticle.dumps(load)}
        self.socket.send_pyobj(payload)
        return self.auth.crypticle.loads(self.socket.recv_pyobj())
