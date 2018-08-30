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

def strip_heredoc(text):
    return '\n'.join([l.strip() for l in text.splitlines()])

class CoastlineEnvironment:
    VARIABLE_PATTERN = re.compile('^(?P<VARIABLE>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<VALUE>.*)"$')
    
    VARIABLE_SETTING_TEMPLATE_ = """
    export HSCT_REAL_CC="$HELENOS_TARGET-gcc"
    export HSCT_REAL_CXX="$HELENOS_TARGET-g++"

    export HSCT_INCLUDE_DIR="$HSCT_BUILD_BASE/include"
    export HSCT_LIB_DIR="$HSCT_BUILD_BASE/lib"

    export HSCT_ARFLAGS="$HELENOS_ARFLAGS"
    export HSCT_CPPFLAGS="-isystem $HSCT_INCLUDE_DIR $HELENOS_CPPFLAGS"
    export HSCT_CFLAGS="$HELENOS_CFLAGS"
    export HSCT_CXXFLAGS="$HELENOS_CXXFLAGS"
    export HSCT_ASFLAGS="$HELENOS_ASFLAGS"
    export HSCT_LDFLAGS="-L $HSCT_LIB_DIR $HELENOS_LDFLAGS"
    export HSCT_LDLIBS="$HELENOS_LDLIBS"
    
    export HSCT_TARGET="$HELENOS_ARCH-helenos"
    export HSCT_CC="$HSCT_TARGET-cc"
    export HSCT_CXX="$HSCT_TARGET-cxx"
    export HSCT_REAL_TARGET="$HELENOS_TARGET"
    export HSCT_CCROSS_TARGET="$HELENOS_ARCH-linux-gnu"
    
    export HSCT_FACADE_DIR="{facade}"

    export PATH="$HSCT_FACADE_DIR:$HELENOS_CROSS_PATH:$PATH"
    """
    
    VARIABLE_SETTING_TEMPLATE = strip_heredoc(VARIABLE_SETTING_TEMPLATE_)
    
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.config = self.load()
    
    def load(self):
        cfg = {}
        with open(os.path.join(self.base_dir, 'helenos', 'config.rc')) as f:
            for line in f:
                m = CoastlineEnvironment.VARIABLE_PATTERN.match(line)
                if m is None:
                    continue
                cfg[m.group("VARIABLE")] = m.group("VALUE")
        return cfg
    
    def get_vars(self):
        output = 'export HELENOS_EXPORT_ROOT="{}"\n'.format(os.path.join(self.base_dir, 'helenos'))
        output = output + 'export HELENOS_BUILD_BASE="{}"\n'.format(self.base_dir)
        for var in self.config:
            output = output + 'export {}="{}"\n'.format(var, self.config[var])
        output = output + '\n\n' + CoastlineEnvironment.VARIABLE_SETTING_TEMPLATE.format(
            facade=os.path.join(self.base_dir, 'facade')
        )
        return output

    def get(self, name, extra_param=None):
        if name == 'build':
            if extra_param is None:
                return os.path.join(self.base_dir, 'build')
            else:
                return os.path.join(self.base_dir, 'build', extra_param)
        elif name == 'sources':
            return os.path.join(self.base_dir, 'sources')
        assert False

class Harbour:
    HARBOUR_SCRIPT_ = """#!/bin/bash
    set -x

    export shipname="{name}"
    export shipversion="{version}"
    export shipfunnels=1
    
    {variables}
    
    run() {{ "$@"; }}
    
    {script}

    (
        cd {harbour_build_dir}
        build
    )

    """
    
    HARBOUR_SCRIPT = strip_heredoc(HARBOUR_SCRIPT_)
    
    def __init__(self, name, base_dir, env):
        self.name = name
        self.base_dir = base_dir
        self.env = env
        
        self.home = os.path.dirname(os.path.realpath(sys.argv[0]))
        self.info = self.load_(name)
    
    def load_(self, name):
        script = ''
        yaml_content = ''
    
        with open(os.path.join(self.home, self.name, 'HARBOUR.yml')) as f:
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
        info['homedir'] = os.path.join(SELF_HOME, self.name)
    
        assert(self.name == info['name'])
    
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
    
    def get_script(self):
        script = Harbour.HARBOUR_SCRIPT.format(
            name=self.name,
            version=self.info['version'],
            variables=self.env.get_vars(),
            script=self.info['script'],
            harbour_build_dir=os.path.join(self.base_dir, 'build', self.name)
        )
        
        return script

    def prebuild(self):
        target_dir = self.env.get('build', self.name)
        os.makedirs(target_dir, exist_ok=True)
        for s in self.info['sources']:
            if s['dest'] == s['url']:
                src = os.path.join(self.home, self.name, s['dest'])
            else:
                src = os.path.join(self.env.get('sources'), s['dest'])
            run_command([
                'ln',
                '-srf',
                src,
                os.path.join(target_dir, s['dest'])
            ])

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

args_build = args_sub.add_parser('build', help='Build given harbour')
args_build.set_defaults(action='build')
args_build.add_argument('harbour',
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

env = CoastlineEnvironment(os.getcwd())

logger = logging.getLogger('main')

if config.action == 'init':
    wd = os.getcwd()
    helenos_dir = os.path.join(wd, 'helenos')
    import_libposix(config.helenos_root[0], helenos_dir)
    install_facade_binaries(os.path.join(wd, 'facade'))
elif config.action == 'fetch':
    harbour = Harbour(config.harbour[0], os.getcwd(), env)
    info = load_harbour(config.harbour[0])
    fetch_sources(info, os.path.join(os.getcwd(), 'sources'))
elif config.action == 'build':
    harbour = Harbour(config.harbour[0], os.getcwd(), env)

    #fetch_sources(info, os.path.join(os.getcwd(), 'sources'))
    #build_harbour(info, os.path.join(os.getcwd(), 'build'))

    harbour.prebuild()
    build_script = harbour.get_script()
    filename = os.path.join(env.get('build'), 'build-{}.sh'.format(harbour.name))
    with open(filename, 'w') as f:
        print(build_script, file=f)
