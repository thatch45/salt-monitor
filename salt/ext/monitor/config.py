import os

import salt.config

def monitor_config(path):
    '''
    Reads the minion configuration file and overrides with values from
    the monitor configuration file.
    '''
    # Load minion config from (1) a file specified by $SALT_MINION_CONFIG or
    # (2) a file named 'minion' in the same directory as the monitor config file.
    minion_config_file = os.environ.get('SALT_MINION_CONFIG')
    if not minion_config_file:
        monitor_config_file = os.environ.get('SALT_MONITOR_CONFIG')
        if monitor_config_file:
            basedir = os.path.dirname(monitor_config_file)
        else:
            basedir = os.path.dirname(path)
        minion_config_file = os.path.join(basedir, 'minion')
    opts = salt.config.minion_config(minion_config_file)

    # Overwrite minion options with monitor defaults
    opts.update({'log_file' : '/var/log/salt/monitor'})

    # Add unset monitor defaults
    for key, value in [('alert_master', 'salt'),
                       ('alert.port', 4507)]:
        if key not in opts:
            opts[key] = value

    # Overlay monitor config on minion config
    salt.config.load_config(opts, path, 'SALT_MONITOR_CONFIG')
    salt.config.prepend_root_dir(opts, ['log_file'])

    # Resolve DNS names to IP addresses
    opts['alert_master'] = salt.config.dns_check(opts['alert_master'])

    return opts

