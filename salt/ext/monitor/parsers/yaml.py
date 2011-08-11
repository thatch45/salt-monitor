#!/usr/bin/env python2

'''
The salt monitor daemon.

The monitor reads configuration from the 'monitor' entry in
/etc/salt/monitor and loops forever running the configured commands at
a user specified interval.

An example configuration is:

    monitor:
      # run every 10 seconds
      - run: status.diskusage /
        every:
          second: 10
        foreach fs, stats:
          - if stats.available * 100 / stats.total > 90:
            - alert.send 'disk usage is above 90% on $fs'

      # run backups every Sunday at 3:27 AM
      - run: backup.backup
        at:
          weekday: sun
          hour: 3
          minute: 27

The configuration is expressed in YAML and must conform to this syntax:

    - run: <salt-command>

      # optional task id or name, e.g. 'id: disk-space-too-low'
      id: <task-id>

      # execute command on an interval
      every:
        day:    <number>
        hour:   <number>
        minute: <number>
        second: <number>

      # execute command at precise date and time
      at:
        month:   <cronlist> # [1-12] or 'jan'-'dec' or 'january'-'december'
        day:     <cronlist> # [1-31]
        weekday: <cronlist> # [1-7] or 'mon'-'sun' or 'monday' - 'sunday'
        hour:    <cronlist> # [0-23]
        minute:  <cronlist> # [0-59]
        second:  <cronlist> # [0-59]

      # iterate over a sorted result dict; result, <key>, and <value>
      # are available within the foreach scope
      foreach <key>, <value>:
        # run commands unconditionally
        - <salt-command>

        # run commands for each item in the list or set result
        - foreach <value>:
          - <salt-commands>

        # run commands if condition is true
        - <condition>:
          - <salt-commands>

        # use if/elif/else logic to select commands to run
        - if <condition>:
          - <salt-commands>
        - elif <condition>:
          - <salt-commands>
        - else:
          - <salt-commands>

      # run command if condition is true; only 'result' is available
      if <condition>:
        - <salt-commands>

where:
    task-id = the task identifier used in error and log messages;
             defaults to 'monitor-#' where # is the command's position in
             /etc/salt/monitor
    salt-command = a shell-like commands line of the command and arguments
    salt-commands = salt commands on separate lines and prefixed with '-'
    number = a integer or floating point number
    key = an arbitrary python identifier used when iterating over the
            dict returned by the salt command
    value = an arbitrary python identifier used when iterating over the
            dict returned by the salt command
    condition = a python expression with optional shell-like $var/${var}
                references.  The variables available include 'result'
                (the result returned from the salt command) and <key>
                and <value> selected by the user.
    cronlist = a list cron items, includes single value (1),
               range (1-3), range plus step (1-3/2), wildcard range (*),
               wildcard range plus step (*/2).  Months and weekdays can
               also be expressed with their locale's full name (monday) or
               abbreviation (mon); names are automatically lowercased.
               Use whitespace and/or commas to separate items.

The 'foreach' statement automatically sorts dict and set results.
If the <value> variable is a dict, foreach automatically wraps <value>
with an AttrDict that allows you to reference the dict contents as
object attributes.  For example, a wrapped value={'foo':1} allows you
to write value.foo or value['foo'].

You must use the shell-like $var and ${expr} references to pass
result, <key>, and <value> data to the salt commands.  For example,
if we had 'foreach k, v:' and wanted to pass the value in k, we'd
write '- mysaltcmd $v'.  If you're trying to pass an element of the
reference, you need to enclose everything in {}s, e.g. use ${v['stuff']}
or ${v.stuff}.  You can also include a python expression in the {}.
For example, ${(v.stuff/10)+100}.

You can format variables and expressions by using ':format' with ${}
references.  For example, ${value:03d} will display 'value' as a three
digit integer, zero padded on the left.  ${value/2.0**30:0.1f} will
divide 'value' by 1 GB and display the result as a floating point
number with one digit after the decimal point and the decimal point
will always be preceeded by at least one digit.  See Python's
string.format() for the format syntax.

Salt command arguments can be enclosed in single or double quotes
to preserve spaces.  For instance, saltcmd 'hi, world' "bob's stuff".

Caveat: since the config is expressed in YAML you must enclose commands
and expressions containing ':' with single quotes.  For example,
    'test.echo "a list: 1, 2, 3"'
'''

# Import python modules
import datetime
import logging
import os
import re
import shlex

# Import salt libs
import salt.log
# notice intra-package references '.'
from ..cron import CronParser
from ..task import MonitorTask

log = salt.log.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 10

class Parser(object):
    '''
    Parser the monitor commands from YAML in /etc/salt/monitor.
    '''
    TOKEN_PATTERN = re.compile(
                r'''(  (?:\\\\)           # match escaped backslash
                     | (?:\\\$)           # match escaped dollar
                     | [{}]               # match braces
                     | (?:\$[A-Za-z_]\w*) # match simple $var
                     | (?:\$\{[^}]+\})    # match expr: ${var}, ${var['name']}
                    )''',
                re.VERBOSE)

    def __init__(self, monitor):
        self.cron_parser      = CronParser()
        self.default_interval = monitor.opts.get('monitor.default_interval',
                                           {'seconds' : DEFAULT_INTERVAL_SECONDS})
        self.functions        = monitor.functions
        self.context          = self._make_context(monitor)
        self.source           = monitor.opts.get('monitor')

    def parse(self):
        return self._expand_tasks(self.source)

    def _make_context(self, monitor):
        result = globals().copy()
        result['id'] = monitor.opts.get('id')
        result['functions'] = monitor.functions
        name = monitor.opts.get('monitor.collector')
        if name:
            result['collector'] = monitor.collectors.get(name)
        return result

    def _expand_tasks(self, parsed_yaml):
        '''
        Assemble compiled code from the configuration described by
        python dictionaries and lists.
        '''
        results = []
        for tasknum, taskdict in enumerate(parsed_yaml, 1):
            try:
                log.trace(taskdict)
                taskid = taskdict.get('id', 'monitor-{}'.format(tasknum))
                pysrc = self._expand_task(taskid, taskdict)
                log.trace("generated '%s' task source:\n%s", taskid, pysrc)
                pyexe = compile(pysrc, '<monitor-config>', 'exec')
                scheduler = self._expand_scheduler(taskdict)
                results.append(MonitorTask(taskid, pyexe, self.context, scheduler))
            except ValueError, ex:
                log.error( 'ignore monitor command #{} {!r}: {}'.format(
                                        tasknum,
                                        taskdict.get('run', '<unknown>'),
                                        ex ) )
        return results

    def _expand_task(self, taskid, taskdict):
        '''
        Translate one task/response dict into an array of python lines.
        '''
        rawtask = taskdict['run']
        cmd = self._split_command(rawtask)
        call = self._expand_call(rawtask)
        result = [
'''
def _run(*args):
    log.trace("{taskid}: run: %s", ' '.join(args))
    ret = functions[args[0]](*args[1:])
    log.trace("{taskid}: result: %s", ret)
    return ret
cmd = {cmd}
result = {call}
'''.format(taskid=taskid,
           cmd=cmd,
           call=call).strip()]

        for key, value in taskdict.iteritems():
            key = key.strip().replace('\t', ' ')
            if key.startswith('foreach '):
                params = key[8:].strip().replace(',', ' ').split()
                result += self._expand_foreach(params, value)
            elif key.startswith('if '):
                result += self._expand_conditional(key, value)
        return '\n'.join(result)

    def _split_command(self, line):
        '''
        Translate one shell-like command line into a python function call.
        For example, "test.echo 'the key is $key'"
            becomes ['test.echo', 'the key is $key']
        '''
        if isinstance(line, dict):
            raise ValueError('cannot use unescaped ":" in salt command line')
        lexer = shlex.shlex(line)
        lexer.whitespace_split = True
        result = [token for token in lexer]
        if len(result) == 0:
            raise ValueError('missing salt command, line: ' + line)
        if result[0] not in self.functions:
            raise ValueError('no such salt command: ' + result[0])
        return result

    def _expand_call(self, line):
        '''
        Expand a parsed command line into a python function call.
        For example, "echo 'the key is $key'"
            becomes "functions['echo']('the key is {}'.format(key))"
        '''
        words = self._split_command(line)
        try:
            args = [repr(words[0])] + [self._expand_references(word, True) for word in words[1:]]
        except ValueError, ex:
            ex.args = (ex.args[0] + ', line: ' + line,)
            raise
        result = '_run({})'.format(', '.join(args))
        return result

    def _expand_foreach(self, params, value):
        '''
        Translate one foreach dict into an array of python lines.
        There are two forms of foreach:
           - "foreach key, value" for dicts
           - "foreach value" for lists and sets
        The user selects the parameter names for key and value.
        For example, "foreach k, v:", "foreach key, value:", or
        "foreach filesystem, stats:".  The user can use either
        the python variable name (e.g. key or k) or the shell-ish name
        (e.g. $key, ${key}, $k, ${key}).
        '''
        names = [self._expand_references(param) for param in params]
        result = []
        if len(names) == 0:
            raise ValueError('foreach missing parameter(s)')
        elif len(names) == 1:
            # foreach over a list or set
            result += [
'''if isinstance(result, set):
    result = sorted(result)
for {} in result:'''.format(*names)]
        elif len(names) == 2:
            # foreach over a dict
            result += [
'''class AttrDict(dict):
    __getattr__ = dict.__getitem__
if not isinstance(result, dict):
    raise ValueError('result is not a dict')
result = AttrDict(result)
for {}, {} in sorted(result.iteritems()):''' \
.format(*names)]
        else:
            raise ValueError('foreach has too many paramters: {}'.format(
                               ', '.join(names)))
        vname = names[-1]
        result += [
'''    if isinstance({0}, dict):
        {0} = AttrDict({0})'''.format(vname)]
        for statement in value:
            if isinstance(statement, basestring):
                result.append('    ' + self._expand_call(statement))
            elif isinstance(statement, dict):
                condition, actions = statement.items()[0]
                result += _indent(self._expand_conditional(condition, actions))
        return result

    def _expand_conditional(self, condition, actions):
        '''
        Translate one if/elif/else dict into an array of python lines.
        '''
        condition = condition.strip().replace('\t', ' ')
        condition = self._expand_references(condition)
        if not condition.startswith(('if ', 'elif ', 'else')):
            condition = 'if ' + condition
        if not condition.endswith(':'):
            condition += ':'
        result = [condition]
        if actions:
            for action in actions:
                result.append('    ' + self._expand_call(action))
        else:
            result.append('    pass')
        return result

    def _expand_references(self, text, to_string=False):
        '''
        Expand the $var, ${var}, and ${expression} references in a string.
        The implementation is a little tricky becasue we allow the user
        to escape dollar signs and backslashes with a backslash (e.g. \$, \\)
        and we need to invisibly escape the braces ({}) used by str.format().
        '''
        fmt = ''
        refs = []
        if len(text) > 1 and text[0] in '\'"' and text[0] == text[-1]:
            quoted = True
            text = text[1:-1]
            to_string = True
        else:
            quoted = False
        for matched in self.TOKEN_PATTERN.split(text):
            if len(matched) == 0:
                pass
            elif len(matched) > 1 and matched.startswith('$'):
                if matched.startswith('${') and matched.endswith('}'):
                    # handle ${var} reference
                    ref = matched[2:-1]
                    if ':' in ref:
                        parts = ref.split(':', 1)
                        ref = "'{{:{1}}}'.format({0})".format(*parts)
                    refs.append(ref)
                else:
                    # handle $var reference
                    refs.append(matched[1:])
                fmt += '{}'
            else:
                # handle plain text
                fmt += matched.replace('\\$', '$') \
                              .replace('\\\\', '\\') \
                              .replace('{', '\1') \
                              .replace('}', '\2')

        if fmt == '{}' and len(refs) == 1:
            result = 'str({})'.format(refs[0]) if quoted else refs[0]
        elif len(refs) == 0:
            fmt = fmt.replace('\1', '{').replace('\2', '}')
            result = repr(fmt) if to_string else fmt
        else:
            fmt = fmt.replace('\1', '{{').replace('\2', '}}')
            result = repr(fmt) + '.format(' + ', '.join(refs) + ')' \
                        if to_string else fmt.format(*refs)
        return result

    def _expand_scheduler(self, taskdict):
        '''
        Create an iterator that generates a sequence of sleep times
        until the next specified event.
        '''
        if 'every' in taskdict:
            sleep_type = 'interval'
            cron_dict = taskdict['every']
        elif 'at' in taskdict:
            sleep_type = 'cron'
            cron_dict = taskdict['at']
        else:
            sleep_type = 'interval'
            cron_dict = self.default_interval
        result = self.cron_parser.create_scheduler(sleep_type, cron_dict)
        return result

def _indent(lines, num_spaces=4):
    '''
    Indent each line in an array of lines.

    >>> _indent(['a','b','c'], 2)
    ['  a', '  b', '  c']
    '''
    indent = ' ' * num_spaces
    result = []
    for line in lines:
        result.append(indent + line)
    return result
