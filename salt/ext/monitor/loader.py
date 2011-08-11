
import os

import salt
import salt.loader
import salt.log

log = salt.log.getLogger(__name__)

def collectors(opts):
    '''
    Returns the returner modules
    '''
    module_dirs = [os.path.join(os.path.dirname(__file__), 'collectors')]
    if 'collector_dirs' in opts:
        module_dirs.append(opts['collector_dirs'])
    load = salt.loader.Loader(module_dirs, opts)
    return load.filter_func('collector')
