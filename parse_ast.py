
import sys
import clang.cindex as cl
import collections

class AstEntry:
    def __init__(self, kind, name, start, end, type_=""):
        self.name = name
        self.kind = kind
        self.type = type_
        self.start = start
        self.end = end
        self.children = []
        self.more = []

def harvest_ast(cursor, keep=lambda k: True):
    def build_entry(cursor):
        return AstEntry(str(cursor.kind), cursor.displayname, cursor.extent.start.line, cursor.extent.end.line, str(cursor.type.kind))

    def build_root():
        return AstEntry("root", "root", 0, 0, "root")

    def process_cursor(cursor, parent_entry):
        if not keep(cursor.kind):
            return None

        new_entry = build_entry(cursor)
        if cursor.is_definition():
            new_entry.more.append(("is_definition", True))
        if cursor.referenced:
            new_entry.more.append(("referenced", cursor.referenced.displayname))

        parent_entry.children.append(new_entry)
        return new_entry

    def walk_tree(cursor, parent_entry, level = 0):
        new_entry = process_cursor(cursor, parent_entry)
        if new_entry:
            parent_entry = new_entry

        for child in cursor.get_children():
            walk_tree(child, parent_entry, level+1)

    root = build_root()
    walk_tree(cursor, root)
    return root

def print_entries(entries):
    def format_entry(e):
        return "{} [{}:{}] [{}:{}] {}".format(e.name, e.kind, e.type, e.start, e.end, e.more if e.more else "")

    def print_entry(root, level = 0):
        print("{}{}".format(level * "  ", format_entry(root)))
        for child in root.children:
            print_entry(child, level+1)

    print_entry(entries)

def harvest_entries(root):
    def walk_tree(entry):
        if entry.kind == "CursorKind.STRUCT_DECL":
            yield entry

        for child in entry.children:
            yield from walk_tree(child)

    yield from walk_tree(root)

class Compiler:
    def __init__(self, source):
        self.source = source
        CLANG_LIB = '/usr/lib/x86_64-linux-gnu/libclang-6.0.so.1'
        cl.Config.set_library_file(CLANG_LIB)

    def get_compile_cmds(self, db_path):
        try:
            compile_db = cl.CompilationDatabase.fromDirectory(db_path)
            return compile_db.getCompileCommands(source)
        except cl.CompilationDatabaseError as e:
            print("PARAM WARNING:")
            print("  Cannot find compilation cmds for {} in {} - ignoring it".format(source, db_path))
            return []

    def compile(self, args=[]):
        try:
            index = cl.Index.create()
            tu = index.parse(source, args=compile_args, options=cl.TranslationUnit.PARSE_INCOMPLETE)
            warnings = list(tu.diagnostics)
            return tu, warnings
        except cl.TranslationUnitLoadError as e:
            return None, str(e)

def clean_compile_cmds(cmds):
    if not cmds:
        return []
    return [a for a in compile_cmds[0].arguments if a.startswith("-I")]

if __name__ == '__main__':
    db_path = sys.argv[1]
    source = sys.argv[2]

    compiler = Compiler(source)
    compile_cmds = compiler.get_compile_cmds(db_path)
    compile_args = clean_compile_cmds(compile_cmds)
    tu, info = compiler.compile(compile_args)
    if not tu:
        print("ERROR: failed to compile because of", info)
        sys.exit(1)
    if info:
        print("COMPILATION WARNINGS:")
        for d in info:
            print(" ", d)
        print()

    interesting_kinds = [ cl.CursorKind.TRANSLATION_UNIT,
            cl.CursorKind.CLASS_DECL,
            cl.CursorKind.CONSTRUCTOR,
            cl.CursorKind.DESTRUCTOR,
            cl.CursorKind.CXX_METHOD,
            cl.CursorKind.FIELD_DECL,
            cl.CursorKind.DECL_REF_EXPR,
            cl.CursorKind.VAR_DECL,
            cl.CursorKind.TYPE_REF,
            cl.CursorKind.MEMBER_REF_EXPR,
            cl.CursorKind.FUNCTION_DECL,
            # cl.CursorKind.CALL_EXPR,
            cl.CursorKind.NAMESPACE,
            cl.CursorKind.STRUCT_DECL,
            cl.CursorKind.PARM_DECL,
            ]

    debug = False
    if debug:
        root = harvest_ast(tu.cursor)
        print_entries(root)
        print()

    root = harvest_ast(tu.cursor, lambda k: k in interesting_kinds)
    print_entries(root)
    print()

    for n in harvest_entries(root):
        print(n.name)
