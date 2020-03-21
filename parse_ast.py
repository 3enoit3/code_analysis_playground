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
import enum

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

def walk_ast(tu, capture_cursor=lambda c, ps: None, walking_poison_pill=None):
    def walk(cursor, parents):
        for capture in capture_cursor(cursor, parents):
            if capture == walking_poison_pill:
                return
            yield capture

        for child in cursor.get_children():
            yield from walk(child, parents + [cursor])

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

def gen_captures(units, capture_cursor, walking_poison_pill):
    for tu in units:
        yield from walk_ast(tu, capture_cursor, walking_poison_pill)

# Captures
class Capture(enum.IntEnum):
    SYMBOL = 0
    REFERENCE = 1

class Reference(enum.IntEnum):
    AGGREGATION = 0
    ASSOCIATION = 1

class Type(enum.IntEnum):
    STRUCT = 0
    TYPEDEF = 1
    UNKNOWN = -1

STOP_WALKING = (None, [])

def location(cursor):
    loc = cursor.location
    if loc and loc.file:
        return os.path.realpath(loc.file.name) + ":" + str(loc.line)
    return "none"

def id_from_type_ref(cursor):
    name = cursor.displayname
    if name.startswith("struct "):
        return name[7:], Type.STRUCT
    if cursor.type.kind == cl.TypeKind.TYPEDEF:
        return name, Type.TYPEDEF
    return name, Type.UNKNOWN

def descendants(cursor):
    yield from itertools.islice(cursor.walk_preorder(), 1, None)

def capture_struct(cursor):
    id = (cursor.displayname, Type.STRUCT)

    yield Capture.SYMBOL, [
            ('id', id),
            ('location', location(cursor))]

    for desc in descendants(cursor):
        if desc.kind == cl.CursorKind.FIELD_DECL:
            for subdesc in descendants(desc):
                if subdesc.kind == cl.CursorKind.TYPE_REF:
                    yield Capture.REFERENCE, [
                            ("from", id),
                            ("to", id_from_type_ref(subdesc)),
                            ("type", Reference.ASSOCIATION if desc.type.kind == cl.TypeKind.POINTER else Reference.AGGREGATION),
                            ("name", desc.displayname)]
                    break
    yield STOP_WALKING

def capture_typedef(cursor):
    id = (cursor.displayname, Type.TYPEDEF)

    def get_origin(cursor):
        for desc in descendants(cursor):
            if desc.kind == cl.CursorKind.TYPE_REF:
                return id_from_type_ref(desc)
            if desc.kind == cl.CursorKind.STRUCT_DECL:
                return desc.displayname, Type.STRUCT

    yield Capture.SYMBOL, [
            ('id', id),
            ('location', location(cursor)),
            ('org', get_origin(cursor))]
    yield STOP_WALKING

# Collect
def collect(captures):
    ids = {}
    aliases = {}
    links = {}
    for capture, props in captures:
        if capture == Capture.SYMBOL:
            new_id = [v for k, v in props if k=="id"][0]

            old_props = ids.get(new_id)
            if old_props:
                if old_props != props:
                    logging.warning("Collision: same id, different properties ({} vs {})".format(props, old_props))
            else:
                ids[new_id] = props

    nodes = [ids[n] for n in sorted(ids.keys())]
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
    path_re = re.compile(args.filter_path)
    def keep_file(path):
        return path_re.search(path) is not None

    def keep_cursor(cursor):
        return cursor.location and cursor.location.file and cursor.location.file.name.startswith(args.codebase_path)

    def capture_cursor(cursor, parents):
        if not cursor.displayname:
            return
        if not keep_cursor(cursor):
            return

        if args.debug:
            logging.debug("{}{} [{}/{}] at {}".format("  " * len(parents),
                cursor.displayname,
                str(cursor.kind),
                str(cursor.type.kind),
                location(cursor)))

        if cursor.kind == cl.CursorKind.STRUCT_DECL and cursor.is_definition():
            yield from capture_struct(cursor)
        if cursor.kind == cl.CursorKind.TYPEDEF_DECL:
            yield from capture_typedef(cursor)

    cmds = (c for c in gen_compile_cmds(args.codebase_path) if keep_file(c.filename))
    units = gen_units(cmds)
    captures = gen_captures(units, capture_cursor, STOP_WALKING)
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
