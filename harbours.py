#!/usr/bin/env python3

#
# Copyright (c) 2018 Vojtech Horky
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# - Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
# - Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
# - The name of the author may not be used to endorse or promote products
#   derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
# OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#


import argparse
import logging
import sys
import os
import subprocess
import shlex
import re
import yaml
from pyparsing import line

SELF_HOME = os.path.dirname(os.path.realpath(sys.argv[0]))

def format_command(cmd):
    """
    Escape shell command given as list of arguments.
    """
    escaped = [shlex.quote(i) for i in cmd]
    return ' '.join(escaped)

def run_command(command, wd=None):
    logger = logging.getLogger('execute')
    logger.debug("{}".format(format_command(command)))
    proc = subprocess.Popen(command, cwd=wd)
    proc.wait()
    if proc.returncode != 0:
        raise Exception("Command {} failed.".format(command))

def load_config():
    VARIABLE_PATTERN = re.compile('^(?P<VARIABLE>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<VALUE>.*)"$')

    cfg = {}
    with open('helenos/config.rc') as f:
        for line in f:
            m = VARIABLE_PATTERN.match(line)
            if m is None:
                continue
            cfg[m.group("VARIABLE")] = m.group("VALUE")
    return cfg

def import_libposix(helenos_root, target_dir):
    logger = logging.getLogger('import_libposix')
    logger.info("Importing libposix headers...")
    run_command([
        'make',
        '-s',
        'export-posix',
        'EXPORT_DIR={}'.format(target_dir),
        'HANDS_OFF=y'
    ], wd=helenos_root)

def install_facade_binaries(target_dir):
    logger = logging.getLogger('install_facade_binaries')
    logger.info("Creating facade binaries...")

    cfg = load_config()
    assert("HELENOS_ARCH" in cfg)

    os.makedirs(target_dir, exist_ok=True)
    for binary in [ "ar", "as", "cc", "cpp", "cxx", "nm", "objcopy", "objdump", "ranlib", "strip" ]:
        facade_binary = '{arch}-helenos-{cmd}'.format(
            arch=cfg["HELENOS_ARCH"],
            cmd=binary,
        )
        run_command([
            'install',
            '-m755',
            os.path.join(SELF_HOME, 'facade', binary),
            os.path.join(target_dir, facade_binary),
        ])


def load_harbour(harbour_name):
    script = ''
    yaml_content = ''

    with open(os.path.join(SELF_HOME, harbour_name, 'HARBOUR.yml')) as f:
        in_yaml = False
        for line in f:
            if line == '---\n':
                in_yaml = True
                continue
            if line == '```\n':
                in_yaml = False
                continue
            if in_yaml:
                yaml_content = yaml_content + line
            else:
                script = script + line

    info = yaml.load(yaml_content)
    info['script'] = script

    assert(harbour_name == info['name'])

    if 'version' not in info:
        info['version'] = ''

    if 'sources' in info:
        sources = []
        for s in info['sources']:
            if type(s) is str:
                s = s.replace('${name}', info['name']).replace('${version}', info['version'])
                src = {
                    'url': s,
                    'dest': os.path.basename(s),
                }
            else:
                continue
            sources.append(src)
        info['sources'] = sources
    else:
        info['sources'] = []

    return info


def fetch_sources(harbour_info, target_dir):
    os.makedirs(target_dir, exist_ok=True)
    for s in harbour_info['sources']:
        dest = os.path.join(target_dir, s['dest'])
        run_command(['wget', s['url'], '-O', dest, '--continue'])

args = argparse.ArgumentParser(
    description='HelenOS coastline (porting POSIX software)'
)
args.set_defaults(action='help')
args_sub = args.add_subparsers(help='Select what to do.')

args_init = args_sub.add_parser('init', help='Initialize new environment')
args_init.set_defaults(action='init')
args_init.add_argument('helenos_root',
    metavar='HELENOS_ROOT_DIR',
    nargs=1,
    help='Path to HelenOS root directory.'
)

args_fetch = args_sub.add_parser('fetch', help='Fetch remote sources for given harbour')
args_fetch.set_defaults(action='fetch')
args_fetch.add_argument('harbour',
    metavar='HARBOUR_NAME',
    nargs=1,
    help='Harbour name.'
)

args.add_argument('--debug',
    dest='debug',
    default=False,
    action='store_true',
    help='Print debugging messages'
)

config = args.parse_args()

if config.debug:
    config.logging_level = logging.DEBUG
else:
    config.logging_level = logging.INFO

logging.basicConfig(
    format='[%(asctime)s %(name)-16s %(levelname)7s] %(message)s',
    level=config.logging_level
)

logger = logging.getLogger('main')

if config.action == 'init':
    wd = os.getcwd()
    helenos_dir = os.path.join(wd, 'helenos')
    import_libposix(config.helenos_root[0], helenos_dir)
    install_facade_binaries(os.path.join(wd, 'facade'))
elif config.action == 'fetch':
    info = load_harbour(config.harbour[0])
    fetch_sources(info, os.path.join(os.getcwd(), 'sources'))
