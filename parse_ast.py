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
        logging.info("walking " + str(tu))
        yield from walk_ast(tu, capture_cursor, walking_poison_pill)
        logging.info("walked " + str(tu))

def gen_unique(captures):
    known = set()
    for type, props in captures:
        key = (type, tuple(props))
        if key not in known:
            known.add(key)
            yield (type, props)

# Captures
class Capture(enum.IntEnum):
    SYMBOL = 0
    REFERENCE = 1

class Reference(enum.IntEnum):
    ASSOCIATION = 0 # flat
    AGGREGATION = 1 # empty diamond
    COMPOSITION = 2 # plain diamond
    GENERALIZATION = 3 # triangle

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
                            ("type", Reference.AGGREGATION if desc.type.kind == cl.TypeKind.POINTER else Reference.COMPOSITION),
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
def get_field(props, field):
    return [v for k, v in props if k == field][0]

def merge(captures):
    symbols = {}
    references = {}

    def add_symbol(props):
        dict_props = dict(props)
        new_id = dict_props["id"]
        old_props = symbols.get(new_id)
        if old_props:
            if old_props != props:
                logging.warning("Collision: same id, different properties ({} vs {})".format(props, old_props))
        else:
            symbols[new_id] = props

    def add_reference(props):
        dict_props = dict(props)
        new_id = (dict_props["from"], dict_props["to"], dict_props["type"])
        references[new_id] = props

    for capture, props in captures:
        if capture == Capture.SYMBOL:
            add_symbol(props)
        elif capture == Capture.REFERENCE:
            add_reference(props)

    return symbols, references

def graph(symbols, references):
    nodes = {}
    symbol_id_to_node_id = {}
    edges = []

    def get_node_id(symbol):
        name, type = get_field(symbol, "id")
        return name + ":" + str(type)

    def add_node(symbol):
        id = get_field(symbol, "id")
        name, type = id
        while type == Type.TYPEDEF:
            # resolve it
            org_id = get_field(symbol, "org")
            if org_id == id:
                break

            org_symbol = symbols.get(org_id)
            if not org_symbol:
                break

            symbol = org_symbol
            id = get_field(symbol, "id")
            name, type = id

        node_id = get_node_id(symbol)
        old_node = nodes.get(node_id)
        if not old_node:
            nodes[node_id] = node_id
        return node_id

    for reference in references.values():
        from_id = get_field(reference, "from")
        from_node_id = add_node(symbols[from_id])
        to_id = get_field(reference, "to")
        to_node_id = add_node(symbols[to_id])
        edges.append((from_node_id, to_node_id, get_field(reference, "type"), get_field(reference, "name")))

    return nodes, edges

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
    else:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)

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
    # captures = gen_unique(captures)
    # with open("captures.txt", "w") as out:
        # for t, p in captures:
            # print(str(t) + ":" + str(p))
            # out.write(str(t) + ":" + str(p) + "\n")
    # return 0

    symbols, references = merge(captures)
    nodes, edges = graph(symbols, references)

    for n in nodes:
        print(n)
    for f, t, a, n in edges:
        print('{} -> {};'.format(f.split(":")[0], t.split(":")[0]))
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
