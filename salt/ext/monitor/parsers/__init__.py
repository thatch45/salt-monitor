import salt.ext.monitor.parsers.yaml

def get_parser(monitor):
    '''
    Find the correct parser based on the monitor configuration.
    Right now we always return a parser that understands
    monitor tasks embedded in the monitor yaml file.
    '''
    return salt.ext.monitor.parsers.yaml.Parser(monitor)
