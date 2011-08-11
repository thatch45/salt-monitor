
import threading

import salt.config
import salt.ext.monitor.loader
import salt.ext.monitor.parsers
import salt.log
import salt.minion

log = salt.log.getLogger(__name__)

class Monitor(salt.minion.SMinion):
    '''
    The monitor daemon.
    '''
    def __init__(self, opts):
        salt.minion.SMinion.__init__(self, opts)
        self.collectors = salt.ext.monitor.loader.collectors(opts)
        if 'monitor' in self.opts:
            parser = salt.ext.monitor.parsers.get_parser(self)
            self.tasks = parser.parse()
        else:
            log.warning('monitor not configured in /etc/salt/monitor')
            self.tasks = []

    def start(self):
        log.debug('starting monitor with {} task{}'.format(
                   len(self.tasks),
                   '' if len(self.tasks) == 1 else 's'))
        if self.tasks:
            for task in self.tasks:
                threading.Thread(target=task.run).start()
        else:
            log.error('no monitor tasks to run')
