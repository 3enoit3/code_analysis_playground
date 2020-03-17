#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Extract symbols from sources using clang"""

import sys
import argparse
import clang.cindex as cl
import itertools
import os
import unittest
import logging
import re

# Ast
CLANG_LIB = '/usr/lib/x86_64-linux-gnu/libclang-6.0.so.1'
cl.Config.set_library_file(CLANG_LIB)

def get_compile_cmds(db_path):
    try:
        compile_db = cl.CompilationDatabase.fromDirectory(db_path)
        return True, compile_db.getAllCompileCommands()
    except cl.CompilationDatabaseError as e:
        return False, "Cannot find compilation cmds in " + db_path

def compile(source, args=[]):
    try:
        index = cl.Index.create()
        tu = index.parse(source, args=args, options=cl.TranslationUnit.PARSE_INCOMPLETE)
        warnings = list(tu.diagnostics)
        return True, (tu, index, warnings)
    except cl.TranslationUnitLoadError as e:
        return False, "Cannot compile because of exception " + str(e)

def walk_ast(tu, capture_cursor=lambda c, ps: None):
    def walk(cursor, parents):
        capture = capture_cursor(cursor, parents)
        if capture:
            yield capture

        for child in cursor.get_children():
            yield from walk(child, parents + [(cursor, capture)])

    yield from walk(tu.cursor, [])

# Generators with side effects
def gen_compile_cmds(db_path):
    ok, extra = get_compile_cmds(db_path)
    if ok:
        cmds = extra
        yield from cmds
    else:
        logging.warning(extra)

def gen_units(cmds):
    for cmd in cmds:
        ok, extra = compile(cmd.filename)
        if ok:
            tu, index, warnings = extra
            if warnings:
                logging.warning("[{}]: {}".format(cmd.filename, list(warnings)))
            yield tu
        else:
            logging.warning("[{}]: {}".format(cmd.filename, extra))

def gen_captures(units, capture_cursor):
    for tu in units:
        yield from walk_ast(tu, capture_cursor)

# Collect
def collect(captures):
    names = {}
    for capture in captures:
        new_name = [v for k, v in capture if k=="name"][0]

        props = names.get(new_name)
        if props:
            if props != capture:
                logging.warning("Collision: same name, different properties ({} vs {})".format(capture, props))
        else:
            names[new_name] = capture

    nodes = [names[n] for n in sorted(names.keys())]
    return nodes

# Main
def main():
    """Entry point"""

    # Parse options
    parser = argparse.ArgumentParser()
    parser.add_argument("codebase_path", type=str,
                        help="path of the codebase")
    parser.add_argument("-f", "--filter_path", type=str, default='.*',
                        help="filter source path")
    parser.add_argument("-d", "--debug", action="store_true", default=False,
                        help="show debug information")
    args = parser.parse_args()

    # Configure debug
    if args.debug:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
        logging.debug("Enabled debug logging")

    # Logic
    filter_re = re.compile(args.filter_path)
    def keep_file(path):
        return filter_re.search(path) is not None

    def keep_cursor(cursor):
        return cursor.location and cursor.location.file and cursor.location.file.name.startswith(args.codebase_path)

    def capture_cursor(cursor, parents):
        if not keep_cursor(cursor):
            return None

        clean_location = lambda loc: os.path.realpath(loc.file.name) + ":" + str(loc.line) if loc and loc.file else "none"

        if args.debug:
            logging.debug("{}{} [{}] at {}".format("  " * len(parents),
                cursor.displayname,
                str(cursor.kind),
                clean_location(cursor.location)))

        if cursor.kind == cl.CursorKind.STRUCT_DECL and cursor.is_definition():
            if cursor.displayname:
                return [('name', cursor.displayname), ('location', clean_location(cursor.location))]
        return None

    cmds = (c for c in gen_compile_cmds(args.codebase_path) if keep_file(c.filename))
    units = gen_units(cmds)
    captures = gen_captures(units, capture_cursor)
    nodes = collect(captures)

    for n in nodes:
        print(n)

    return 0

if __name__ == "__main__":
    sys.exit(main())

class Tests(unittest.TestCase):
    # pylint: disable=too-many-public-methods
    """Unit tests"""
    # run test suite with
    # python -m unittest <this_module_name_without_py_extension>

    def setUp(self):
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    def test(self):
        """Scenario"""
        self.assertTrue(True is True)
        self.assertEqual(True, True)
