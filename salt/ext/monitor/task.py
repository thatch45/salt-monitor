import datetime
import time

import salt.log

log = salt.log.getLogger(__name__)

class MonitorTask(object):
    '''
    A single monitor task.
    '''
    def __init__(self, taskid, pyexe, context, scheduler=None):
        self.taskid    = taskid
        self.code      = pyexe
        self.context   = context
        self.scheduler = scheduler

    def run(self):
        log.trace('start thread for %s', self.taskid)
        minion = self.context.get('id')
        collector = self.context.get('collector')
        while True:
            try:
                exec self.code in self.context
            except Exception, ex:
                log.error("can't execute %s: %s", self.taskid, ex, exc_info=ex)
            if collector:
                jid = datetime.datetime.strftime(
                             datetime.datetime.now(), 'M%Y%m%d%H%M%S%f')
                try:
                    collector(minion, self.context['cmd'], self.context['result'])
                except Exception, ex:
                    log.error('monitor error: %s', self.taskid, exc_info=ex)
            if self.scheduler is None:
                break
            duration = self.scheduler.next()
            log.trace('%s: sleep %s seconds', self.taskid, duration)
            time.sleep(duration)
        log.debug('thread exit: %s', self.taskid)
