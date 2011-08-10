import datetime
import time

import salt.log

ALL_RESULTS_VARIABLE = "task_results"

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
        returner = self.context.get('returner')
        while True:
            try:
                exec self.code in self.context
            except Exception, ex:
                log.error("can't execute %s: %s", self.cmdid, ex, exc_info=ex)
            if returner:
                jid = datetime.datetime.strftime(
                             datetime.datetime.now(), 'M%Y%m%d%H%M%S%f')
                try:
                    returner({'id' : minion,
                              'jid' : jid,
                              'return' : self.context[ALL_RESULTS_VARIABLE]})
                except Exception, ex:
                    log.error('monitor error: %s', self.taskid, exc_info=ex)
            if self.scheduler is None:
                break
            duration = self.scheduler.next()
            log.trace('%s: sleep %s seconds', self.taskid, duration)
            time.sleep(duration)
        log.debug('thread exit: %s', self.taskid)
