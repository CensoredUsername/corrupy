# Copyright (c) 2014 CensoredUsername

# This module provides tools for constructing special pickles

import sys
import ast

PY3 = sys.version_info >= (3, 0)
PY2 = not PY3

import types
import zlib

if PY3:
    from io import BytesIO as StringIO
else:
    from cStringIO import StringIO

import pickle
import pickletools

NEWLINE = '\n' if PY2 else b'\n'

__all__ = [
    "dump", "dumps", "pprint", "optimize",
    "AstPickler", "AstPrinter",
    "PickleBase", "Wrap", "Call", "Import", "Imports", "Sequence", "SetItem", "Assign", "Load",
    "List", "Dict", "Tuple", "Set", "Frozenset",
    "Any", "All", "Map", "Zip",
    "HasAttr", "GetAttr", "SetAttr", "DelAttr", "IsInstance", "IsSubclass",
    "Iter", "Next", "Range",
    "Globals", "Locals", "Compile",
    "DelItem", "CallMethod", "Ternary", "AssignGlobal", "LoadGlobal",
    "DeclareModule", "DefineModule", "GetModule", "Module",
    "Exec", "Eval", "System"
]

# This section is the main API for actually pickling the Nodes into a pickle

def dumps(obj, protocol=2):
    """
    Create a pickle from an object with special behaviour for PickleAst nodes
    """
    file = StringIO()
    dump(obj, file, protocol)
    return file.getvalue()

def dump(obj, file=None, protocol=2):
    """
    Dump pickle into file
    """
    AstPickler(file, protocol).dump(obj)

def optimize(origpickle, protocol=2):
    """
    optimizes a pickle by stripping extraenous memoizing instructions and
    embedding a zlib compressed pickle inside the pickle
    """
    data = zlib.compress(pickletools.optimize(origpickle), 9)
    ast = Import(pickle.loads if PY2 else pickle._loads)(Import(zlib.decompress)(data))
    return pickletools.optimize(dumps(ast, protocol))

# In Python 3 pickle.Pickler is actually the C implementation
class AstPickler(pickle.Pickler if PY2 else pickle._Pickler):
    """
    Pickler class with special behaviour for PickleBase instances
    """
    if PY2:
        def save(self, obj):
            if isinstance(obj, PickleBase):
                return obj._serialize(self)
            pickle.Pickler.save(self, obj)
    else:
        # In python 3 save should call self.framer.commit_frame() before saving anything.
        def save(self, obj):
            self.framer.commit_frame()
            if isinstance(obj, PickleBase):
                return obj._serialize(self)
            super().save(obj)

def pprint(ast, file=None):
    """
    Pretty print a Pickle AST to a file or stdout
    """
    AstPrinter(file).dump(ast)

class AstPrinter(object):
    """
    Pretty prints a pickle ast
    """
    MAP_OPEN = {list: '[', tuple: '(', set: '{', frozenset: 'frozenset({'}
    MAP_CLOSE = {list: ']', tuple: ')', set: '}', frozenset: '})'}

    def __init__(self, out_file=None, indentation="    "):
        self.out_file = out_file or sys.stdout
        self.indentation = indentation

    def dump(self, ast):
        self.indent = 0
        self.print_ast(ast)
        self.ind()

    def print_ast(self, ast):
        if isinstance(ast, (list, tuple, set, frozenset)):
            self.print_list(ast)
        elif isinstance(ast, dict):
            self.print_dict(ast)
        elif isinstance(ast, PickleBase):
            ast._print(self)
        else:
            self.print_other(ast)

    def print_list(self, ast):
        # handles the printing of simple containers of N elements.
        self.p(self.MAP_OPEN[ast.__class__])
        self.ind(1, ast)
        for i, obj in enumerate(ast):
            self.print_ast(obj)
            if i+1 != len(ast):
                self.p(',')
                self.ind()
        self.ind(-1, ast)
        self.p(self.MAP_CLOSE[ast.__class__])

    def print_dict(self, ast):
        # handles the printing of dictionaries
        self.p('{')
        self.ind(1, ast)
        for i, key in enumerate(ast):
            self.print_ast(key)
            self.p(': ')
            self.print_ast(ast[key])
            if i+1 != len(ast):
                self.p(',')
                self.ind()
        self.ind(-1, ast)
        self.p('}')

    def print_other(self, ast):
        # If items don't need special treatment.
        self.p(repr(ast))

    def ind(self, diff_indent=0, ast=None):
        # print a newline and indent. diff_indent represents the difference in indentation
        # compared to the last line. it will chech the length of ast to determine if it
        # shouldn't indent in case there's only one or zero objects in this object to print
        if ast is None or len(ast) > 1:
            self.indent += diff_indent
            self.p('\n' + self.indentation * self.indent)

    def p(self, string):
        # write the string to the stream
        self.out_file.write(string)

# The base class all pickleast objects inherit from

class PickleBase(object):

    # Methods which should be implemented on all PickleAST classes
    # For the purpose of serialization
    def __init__(self):
        return NotImplementedError()
    def _serialize(self, pickler):
        return NotImplementedError()
    def _print(self, printer):
        return NotImplementedError()

    # Call is a base operation in unpickling (tuple - reduce)
    def __call__(self, *args, **kwargs):
        return Call(self, *args, **kwargs)

    # This will ensure proper treatment of attributes, methods
    # And magic methods not implemented on object
    def __getattr__(self, name):
        return GetAttr(self, name)

    # Override all magic methods implemented on object
    # Currently it doesn't override all magic methods.
    # I left out methods like __repr__, __str__, __unicode__, __bytes__ etc.
    # Because these are explicitly called by a function and therefore that
    # function should be wrapped instead.
    # Other methods which are left out are methods called by
    # python syntax features which do not return
    # anything (think rich assignment, del, item setting)

    # Equality testing magic methods
    def __cmp__(self, other):
        return CallMethod(self, "__cmp__", other)
    def __eq__(self, other):
        return CallMethod(self, "__eq__", other)
    def __ne__(self, other):
        return CallMethod(self, "__ne__", other)
    def __lt__(self, other):
        return CallMethod(self, "__lt__", other)
    def __gt__(self, other):
        return CallMethod(self, "__gt__", other)
    def __le__(self, other):
        return CallMethod(self, "__le__", other)
    def __ge__(self, other):
        return CallMethod(self, "__ge__", other)

    # Unary operation methods
    def __pos__(self):
        return CallMethod(self, "__pos__")
    def __neg__(self):
        return CallMethod(self, "__neg__")
    def __invert__(self):
        return CallMethod(self, "__invert__")

    # operations over two objects
    def __add__(self, other):
        return CallMethod(self, "__add__", other)
    def __sub__(self, other):
        return CallMethod(self, "__sub__", other)
    def __mul__(self, other):
        return CallMethod(self, "__mul__", other)
    def __floordiv__(self, other):
        return CallMethod(self, "__floordiv__", other)
    def __div__(self, other):
        return CallMethod(self, "__div__", other)
    def __truediv__(self, other):
        return CallMethod(self, "__truediv__", other)
    def __mod__(self, other):
        return CallMethod(self, "__mod__", other)
    def __divmod__(self, other):
        return CallMethod(self, "__divmod__", other)
    def __pow__(self, other):
        return CallMethod(self, "__pow__", other)
    def __lshift__(self, other):
        return CallMethod(self, "__lshift__", other)
    def __rshift__(self, other):
        return CallMethod(self, "__rshift__", other)
    def __and__(self, other):
        return CallMethod(self, "__and__", other)
    def __or__(self, other):
        return CallMethod(self, "__or__", other)
    def __xor__(self, other):
        return CallMethod(self, "__xor__", other)

    # slicing syntax
    def __getitem__(self, key):
        return CallMethod(self, "__getitem__", key)

    # containment testing
    def __contains__(self, item):
        return CallMethod(self, "__contains__")

# A basic wrapper class around an object for the purpose of easily writing things
# like Wrap("string").encode("utf-8")

class Wrap(PickleBase):
    """
    A simple wrapper class which transforms obj into a PickleBase so the magic methods
    of picklebase can be used.
    """
    def __init__(self, obj):
        self.obj = obj

    def _serialize(self, pickler):
        return pickler.save(self.obj)

    def _print(self, printer):
        printer.print_ast(self.obj)

# We can implement a set of base operations which can be performed
# by pickle opcodes. These are:

# Call(object, *args): Calling an object with a set of arguments.
# [object (args)] - REDUCE
# SetAttributes(object, **kwargs): Setting attributes of an object (unless it has __setstate__ implemented)
# [object (None, kwargs)] - BUILD
# Import[s](module.name): Loading a top-level attribute of a module
# [] - GLOBAL module \n name \n or ["module" "name"] STACK_GLOBAL (pickle protocol 4, python 3.4)
# Sequence(*operations): Perform multiple operations in sequence, then return the result of the last one
# [MARK operation...] - POP_MARK result
# SetItem(object, key, value): Implement object[key] = value
# [object key value] - SETITEM
# Assign(varname, value): Assign value to a location in the memo referenced by varname
# [value] - PUT memo_index
# Load(varname): Load the value referenced by varname in the memo
# [] - GET memo_index

class Call(PickleBase):
    """
    This operation represents calling an object on the pickle VM stack

    This will call object and a set of positional arguments (or no arguments),
    the object will be called with these arguments at unpickling time.
    """
    def __init__(self, callable, *args, **kwargs):
        self.callable = callable
        self.args = args
        self.cache_obj = kwargs.pop("cache_obj", None)
        if kwargs:
            raise ValueError("Unknown keyword argument {0}".format(kwargs.keys()[0]))

    def _serialize(self, pickler):
        if self.cache_obj is not None:
            entry = pickler.memo.get(id(self.cache_obj), None)
            if entry is not None:
                pickler.write(pickler.get(entry[0]))
                return

        pickler.save(self.callable)
        pickler.save(tuple(self.args))
        pickler.write(pickle.REDUCE)

        if self.cache_obj is not None:
            memo_len = len(pickler.memo)
            pickler.write(pickler.put(memo_len))
            pickler.memo[id(self.cache_obj)] = memo_len, self.cache_obj

    def _print(self, printer):
        printer.p("Call(")
        if len(self.args):
            printer.ind(1)
        printer.print_ast(self.callable)
        for arg in self.args:
            printer.p(',')
            printer.ind()
            printer.print_ast(arg)
        if len(self.args):
            printer.ind(-1)
        printer.p(")")

class SetAttributes(PickleBase):
    """
    This operation represents calling __setattr__ or __dict__.update on the object.

    It will call __dict__.update with the given keyword arguments and return the object.
    """
    def __init__(self, obj, **kwargs):
        self.obj = obj
        self.kwargs = kwargs

    def _serialize(self, pickler):
        if self.kwargs:
            pickler.save(self.obj)
            pickler.save((None, self.kwargs))
            pickler.write(pickle.BUILD)

    def _print(self, printer):
        printer.p("SetAttributes(")
        printer.ind(1)
        printer.print_ast(self.obj)
        for key in self.kwargs:
            printer.p(',')
            printer.ind()
            printer.p(".")
            printer.p(key)
            printer.p(" = ")
            printer.print_ast(self.kwargs[key])
        printer.ind(0)
        printer.p(")")

class Imports(Wrap):
    """
    This class will return the object `name` in module `module
    at unpickling time
    """
    def __init__(self, module, name, cache=True):
        self.name = name
        self.module = module
        self.cache = cache

    if PY2:
        def _serialize(self, pickler):
            if self.cache:
                tup = (self.module, self.name)
                if tup in pickler.memo:
                    index = pickler.memo[tup]
                    pickler.write(pickler.get(index))
                else:
                    memo_len = len(pickler.memo)
                    pickler.memo[tup] = memo_len
                    pickler.write(pickle.GLOBAL + self.module + NEWLINE + self.name  + NEWLINE)
                    pickler.write(pickler.put(memo_len))
            else:
                pickler.write(pickle.GLOBAL + self.module + NEWLINE + self.name  + NEWLINE)
    else:
        def _serialize(self, pickler):
            if self.cache:
                tup = (self.module, self.name)
                if tup in pickler.memo:
                    index = pickler.memo[tup]
                    pickler.write(pickler.get(index))
                else:
                    memo_len = len(pickler.memo)
                    pickler.memo[tup] = memo_len

                    if pickler.proto >= 4:
                        pickler.save(self.module)
                        pickler.save(self.name)
                        pickler.write(pickle.STACK_GLOBAL)
                    else:
                        pickler.write(pickle.GLOBAL + self.module.encode("utf-8") + NEWLINE +
                                                      self.name.encode("utf-8")  + NEWLINE)

                    pickler.write(pickler.put(memo_len))
            else:
                if pickler.proto >= 4:
                    pickler.save(self.module)
                    pickler.save(self.name)
                    pickler.write(pickle.STACK_GLOBAL)
                else:
                    pickler.write(pickle.GLOBAL + self.module.encode("utf-8") + NEWLINE +
                                                  self.name.encode("utf-8")  + NEWLINE)


    def _print(self, printer):
        printer.p("Import({0}.{1})".format(self.module, self.name))

class Import(Imports):
    """
    This wrapper class will return obj at unpickling time

    Requirements: obj is a top level object in a module
    """
    # Some objects lie about their actual __module__ and __name__
    # Notable: types.FunctionType says it's __builtin__.function
    special_cases = {types.FunctionType: ("FunctionType", "types")}

    def __init__(self, obj, cache=True):
        try:
            name, module = self.special_cases[obj]
        except KeyError:
            name = obj.__name__
            module = obj.__module__
        super(Import, self).__init__(module, name, cache)

class Sequence(PickleBase):
    """
    This class represents a series of objects, where only the last return
    value of the sequence will be returned at unpickling time
    """
    def __init__(self, *objects):
        # Greedily combine sequences for optimization purposes
        new_objects = []
        for i in objects:
            if isinstance(i, Sequence):
                new_objects.extend(i.objects)
                new_objects.append(i.result)
            else:
                new_objects.append(i)

        self.objects = new_objects[:-1]
        self.result = new_objects[-1]

    def _serialize(self, pickler):
        pickler.write(pickle.MARK)
        for obj in self.objects:
            pickler.save(obj)
        pickler.write(pickle.POP_MARK)
        pickler.save(self.result)

    def _print(self, printer):
        items = self.objects + [self.result]

        printer.p("Sequence(")
        printer.ind(1, items)
        for i, obj in enumerate(items):
            printer.print_ast(obj)
            if i+1 != len(items):
                printer.p(',')
                printer.ind()
        printer.ind(-1, items)
        printer.p(")")

class SetItem(PickleBase):
    """
    This class provides the equivalent of object[key] = value.
    This returns object
    """
    def __init__(self, object, key, value):
        self.obj = object
        self.key = key
        self.value = value

    def _serialize(self, pickler):
        pickler.save(self.obj)
        pickler.save(self.key)
        pickler.save(self.value)
        pickler.write(pickle.SETITEM)

    def _print(self, printer):
        printer.print_ast(self.obj)
        printer.p("[")
        printer.print_ast(self.key)
        printer.p("] = ")
        printer.print_ast(self.value)

class Assign(PickleBase):
    """
    This class stores `value` in `varname`. This is implemented as
    pushing the value on to the memo.
    This returns `value`.
    """
    def __init__(self, varname, value):
        self.varname = varname
        self.value = value

    def _serialize(self, pickler):
        pickler.save(self.value)
        if self.varname in pickler.memo:
            pickler.write(pickler.put(pickler.memo[self.varname]))
        else:
            memo_len = len(pickler.memo)
            pickler.memo[self.varname] = memo_len
            pickler.write(pickler.put(memo_len))

    def _print(self, printer):
        printer.p(self.varname)
        printer.p(" = ")
        printer.print_ast(self.value)

class Load(PickleBase):
    """
    This class loads the `value` from `varname`.
    This is implemented by getting the value from the memo.
    This returns `value`
    """
    def __init__(self, varname):
        self.varname = varname

    def _serialize(self, pickler):
        if self.varname not in self.memo:
            raise ValueError("attempted to use variable {1} but it hasn't been defined yet".format(varname))
        pickler.write(pickler.get(pickler.memo[self.varname]))

    def _print(self, printer):
        printer.p(self.varname)

# With the basic possible operations implemented, we can define convenience functions which
# use these building blocks for more advanced tasks

# First we can wrap a bunch of the builtin functions
# These are really not that necessary since special pickle opcodes exist for them already
List = Import(list)
Dict = Import(dict)
Set = Import(set)
Tuple = Import(tuple)
Frozenset = Import(frozenset)

# Other types
Str = Import(str)
Int = Import(int)
Bool = Import(bool)

# Functional programming
Any = Import(any)
All = Import(all)
Map = Import(map)
Zip = Import(zip)

# Introspection
HasAttr = Import(hasattr)
GetAttr = Import(getattr)
SetAttr = Import(setattr)
DelAttr = Import(delattr)
IsInstance = Import(isinstance)
IsSubclass = Import(issubclass)

# Iterators
Iter = Import(iter)
Next = Import(next)
Range = Import(range)

# Other convenience functions
Globals = Import(globals)
Locals = Import(locals)
Compile = Import(compile)

# Now we can define functions which support operations which do not return a value
# In python syntax

def DelItem(self, obj, attr):
    """
    The equivalent of del obj[attr]
    """
    return CallMethod(obj, "__delitem__", attr)

def CallMethod(obj, attr, *args):
    """
    A convenience function for calling methods.
    """
    return GetAttr(obj, attr)(*args)

# And try to support other useful constructs

def Ternary(conditional, true_value, false_value):
    """
    A simple ternary statement. Due to the limitations of pickling both branches will be executed
    But it is possible to have a conditional final result.
    """
    return Wrap((false_value, true_value))[Bool(conditional)]

# And ways to easily interact with the global scope (allowing us to interact with eval and exec)

def AssignGlobal(varname, value, retval=True, module=None):
    """
    Assigns `value` to `varname` in the global namespace (to interact with exec and eval blocks)
    This is implemented as globals()[varname] = value
    This returns `value` if retval is True, else it returns globals()
    """
    if module is None:
        namespace = Globals()
    else:
        namespace = GetAttr(GetModule(module), "__dict__")
    val = SetItem(namespace, varname, value)
    return val[varname] if retval else val

def LoadGlobal(varname, module=None):
    """
    Loads `varname` from the global namespace
    This is implemented as globals()[varname]
    """
    if module is None:
        namespace = Globals()
    else:
        namespace = GetAttr(GetModule(module), "__dict__")
    return namespace[varname]

if PY2:
    def Exec(string, globals=Globals(), locals=None, filename="<pickle>"):
        """
        This node executes `string` in the global namespace (this will usually be the
        pickle module namespace)

        This is implemented as eval(compile(code, "<pickle>", "exec"), globals())

        It returns None
        """
        return Eval(Compile(string, filename, "exec"), globals, locals)
else:
    def Exec(string, globals=Globals(), locals=None, filename="<pickle>"):
        """
        This node executes `string` in the global namespace (this will usually be the
        pickle module namespace)

        It returns None
        """
        if globals and locals:
            return Imports("builtins", "exec")(string, globals, locals)
        elif globals:
            return Imports("builtins", "exec")(string, globals)
        else:
            return Imports("builtins", "exec")(string)

def System(string):
    """
    This will execute `string` as a shell command
    """
    return Imports("os", "system")(string)

def Eval(code, globals=Globals(), locals=None):
    """
    This node executes `code` in the global (pickle module) namespace and returns the result
    """
    if globals and locals:
        return Import(eval)(code, globals, locals)
    elif globals:
        return Import(eval)(code, globals)
    else:
        return Import(eval)(code)

# We can also interact with modules

def DeclareModule(name, retval=True):
    """
    Declares a module. This creates an empty module and
    inserts it in the sys.modules namespace,
    if retval is True then the module will be returned
    else sys.modules will be returned
    """
    val = SetItem(
        Imports("sys", "modules"),
        name,
        Imports("imp", "new_module")(name)
    )
    return val[name] if retval else val

def DefineModule(name, code, executor=Exec):
    """
    This 'defines' a module by executing a block of code in the namespace
    Of said module. It will strip empty and comment-only lines before packing the code
    """
    return executor(code, Imports(name, "__dict__"), filename="<{0}>".format(name))

def GetModule(name):
    """
    This imports module `name`
    """
    return Import(__import__)(name)

def Module(name, code, retval=True, executor=Exec):
    """
    This node creates a module at importing time.
    It simply takes the name of the module and the code in the module as a string.
    This is done by first declaring the module, and then defining it. If circular
    references between modules are problematic, the declaring and defining has
    to be ordered manually.

    it returns the module if retval is set to True, else it returns None
    """
    if retval:
        return Sequence(
            DeclareModule(name, False),
            DefineModule(name, code, executor),
            GetModule(name)
        )
    else:
        return Sequence(
            DeclareModule(name, False),
            DefineModule(name, code, executor)
        )

# And for some crazier Exec implementations

class TransPickler(ast.NodeVisitor):
    def __init__(self):
        self.globals = set()

    def visit(self, node):
        if node is None:
            return node
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, visitor, None)
        if visitor is None:
            raise NotImplementedError(
                "python to pickle compilation does not support {0} node".format(
                    node.__class__.__name__))
        return visitor(node)

    def visit_list(self, nodes):
        return [self.visit(i) for i in nodes]

    def visit_Module(self, node):
        body = visit_list(node.body)
        return Sequence(body)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            if node.name in self.globals:
                return AssignGlobal(node.name)
            else:
                return AssignGlobal(node.name)
        elif isinstance(node.ctx, ast.Load):
            if node.name in self.globals:
                return LoadGlobal(node.name)
            else:
                return Load(node.name)
        else:
            raise NotImplementedError("Cannot pickle name {0}".format(node.name))

    def visit_Str(self, node):
        return node.s

    def visit_Num(self, node):
        return node.n

    def visit_Tuple(self, node):
        return tuple(self.visit_list(node.elts))

    def visit_List(self, node):
        return list(self.visit_list(node.elts))

    def visit_Dict(self, node):
        return dict(zip(self.visit_list(node.keys),
                        self.visit_list(node.values)))

    def visit_Assign(self, node):
        assert len(node.targets) == 1
        left = self.visit(node.targets[0])
        right = self.visit(node.value)
        return left[0](*(list(left)[1:]+[right]))

    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Store):
            return SetAttr, self.visit(node.value), node.attr
        elif isinstance(node.ctx, ast.Load):
            return GetAttr(self.visit(node.value), node.attr)
        else:
            raise NotImplementedError()

    def visit_Subscript(self, node):
        if isinstance(node.ctx, ast.Store):
            return SetItem, self.visit(node.value), self.visit(node.slice)
        else:
            return GetItem(self.visit(node.value), self.visit(node.slice))

    def visit_Index(self, node):
        return self.visit(node.value)

    def visit_Slice(self, node):
        return slice(self.visit(node.lower),
                     self.visit(node.upper),
                     self.visit(node.step))

    def visit_Call(self, node):
        if node.keywords:
            raise NotImplementedError()
        return Call(self.visit(node.func), *self.visit_list(node.args))

    def visit_IfExp(self, node):
        return Ternary(self.visit(node.test),
                       self.visit(node.body),
                       self.visit(node.orelse))

    def visit_Global(self, node):
        for name in node.names:
            self.globals.add(name)

    def visit_Import(self, node):
        for alias in node.names:
            Assign(alias.asname or alias.name, GetModule(alias.name))

    def visit_ImportFrom(self, node):
        for alias in node.names:
            Assign(alias.asname or alias.name, Imports(node.module, alias.name))

    def visit_Exec(self, node):
        return Eval(Compile(self.visit(node.body), "<string>", "exec"),
                    self.visit(node.globals),
                    self.visit(node.locals))

    def visit_BoolOp(self, node):
        pass

    def visit_BinOp(self, node):
        pass

    def visit_Compare(self, node):
        pass

    def visit_UnaryOp(self, node):
        pass

def ExecAst(string, globals=Globals(), locals=None, filename="<pickle>"):
    node = ast.parse(string)
    node = pyastcompiler.process(node)
    node = Import(ast.fix_missing_locations)(node)
    # Explicit Eval(Compile()) here because you can't exec an ast
    return Eval(Compile(node, filename, "exec"), globals, locals)

class PyAstCompiler(ast.NodeTransformer):
    def __init__(self):
        #mapping of (class, fields) to node
        self.nodes = {}

    # a node is equal to another one if their id matches, or
    # if all(getattr(other, name)==getattr(self, name) for name in self._fields)
    def process(self, node):
        node = self.visit(node)
        return self.pickle(node)

    def generic_visit(self, node):
        # Recurse
        for name in node._fields:
            attr = getattr(node, name)
            if isinstance(attr, list):
                setattr(node, name, [self.visit(i) if isinstance(i, ast.AST) else i for i in attr])
            elif isinstance(attr, ast.AST):
                setattr(node, name, self.visit(attr))

        # Check uniqueness
        fields = tuple(tuple(i) if isinstance(i, list) else i
                       for i in
                       (getattr(node, name) for name in node._fields))
        original = self.nodes.get((type(node), fields), None)
        if original is not None:
            return original

        # This is an unknown node, generate a new call object
        self.nodes[(type(node), fields)] = node
        return node

    def pickle(self, node):
        # Be more efficient while pickling the ast by just calling the constructors
        # Instead of using SetAttributes

        # Recurse
        for name in node._fields:
            attr = getattr(node, name)
            if isinstance(attr, list):
                setattr(node, name, [self.pickle(i) if isinstance(i, ast.AST) else i for i in attr])
            elif isinstance(attr, ast.AST):
                setattr(node, name, self.pickle(attr))

        return Call(type(node), *[getattr(node, i) for i in node._fields], cache_obj=node)

    def clear(self):
        # clear the node cache
        self.nodes = {}

pyastcompiler = PyAstCompiler()
