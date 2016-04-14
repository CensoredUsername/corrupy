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
import operator
from struct import pack

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


# Pretty printing (mainly for debugging reasons)
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

    # Call is a base operation in unpickling (tuple - reduce). To make this module
    # a bit better to read we allow generating Call nodes just by calling a PickleBase object
    def __call__(self, *args, **kwargs):
        return Call(self, *args, **kwargs)

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
# by pickle opcodes. These are (formatting: [items on stack] - opcodes):

# Call(object, *args): Calling an object with a set of arguments.
# [object (args)] - REDUCE

# SetAttributes(object, **kwargs): Setting attributes of an object (unless it has __setstate__ implemented)
# [object (None, kwargs)] - BUILD

# Import[s](module.name): Loading a top-level attribute of a module
# [] - GLOBAL module \n name \n or ["module" "name"] STACK_GLOBAL (pickle protocol 4, python 3.4)

# Sequence(*operations, result): Perform multiple operations in sequence, then return the result of the last one
# [MARK operation...] - POP_MARK result
# [operation] - POP result

# SetItem(object, key, value): Implement object[key] = value
# [object key value] - SETITEM

# Assign(varname, value): Assign value to a location in the memo referenced by varname
# [value] - PUT memo_index

# Load(varname): Load the value referenced by varname in the memo
# [] - GET memo_index

# These are the only "native" operations available to us from the pickle stream. However, we can
# use them to construct many more operations using functions available in the builtins module

class Call(PickleBase):
    """
    This operation represents calling an object on the pickle VM stack

    This will call object and a set of positional arguments (or no arguments),
    the object will be called with these arguments at unpickling time.
    """
    def __init__(self, callable, *args):
        self.callable = callable
        self.args = args

    def _serialize(self, pickler):
        pickler.save(self.callable)
        pickler.save(tuple(self.args))
        pickler.write(pickle.REDUCE)

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
    value of the sequence will be returned at unpickling time.
    if `reversed` is True then the first object will be returned instead of the last object.
    """
    def __init__(self, *objects, **kwargs):
        self.reversed = kwargs.pop("reversed", False)
        if kwargs:
            raise TypeError("__init__ got too many keyword arguments: {}".format(kwargs))

        # Greedily combine sequences for optimization purposes
        # note: reversed sequences can be safely merged as long as they are not the last item in 
        # a non-reversed sequence. Similarly, a non-reversed sequence can be safely merged as long
        # as it is not the first item in a reversed sequence.
        self.objects = []
        for i, obj in enumerate(objects):
            if isinstance(obj, Sequence) and (obj.reversed == self.reversed or                # both sequences have the same direction
                                              (self.reversed and i) or                        # or this is not the first item in a reversed sequence
                                              (not self.reversed and i != len(objects) - 1)): # or this is not the last item in a non-reversed sequence
                self.objects.extend(obj.objects)
            else:
                self.objects.append(obj)

    def _serialize(self, pickler):
        if not self.objects:
            raise ValueError("Empty sequence")

        if len(self.objects) == 1:
            pickler.save(self.objects[0])

        elif len(self.objects) == 2:
            pickler.save(self.objects[0])
            if self.reversed:
                pickler.save(self.objects[1])
                pickler.write(pickle.POP)
            else:
                pickler.write(pickle.POP)
                pickler.save(self.objects[1])

        else:
            for i, obj in enumerate(self.objects):
                if i == (1 if self.reversed else 0):
                    pickler.write(pickle.MARK)

                pickler.save(obj)

                if len(self.objects) - i == (1 if self.reversed else 2):
                    pickler.write(pickle.POP_MARK)

    def _print(self, printer):
        items = self.objects

        printer.p("RevSequence(" if self.reversed else "Sequence(")
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
        if self.varname not in pickler.memo:
            raise ValueError("attempted to use variable {0} but it hasn't been defined yet".format(self.varname))
        pickler.write(pickler.get(pickler.memo[self.varname]))

    def _print(self, printer):
        printer.p(self.varname)

# With the basic possible operations implemented, we can define convenience functions which
# use these building blocks for more advanced tasks

# First we can wrap a bunch of the builtin functions
# Note: these functions do not use the native picle stream operations to construct them. They actually call the functions.
List = Import(list)
Dict = Import(dict)
Set = Import(set)
Tuple = Import(tuple)
Frozenset = Import(frozenset)

# Other types
Str = Import(str)
Int = Import(int)
Bool = Import(bool)

# Functional programming. Useful since we cannot have any control flow
Any = Import(any)
All = Import(all)
Map = Import(map)
Zip = Import(zip)

# Introspection. These grant us access to attribute manipulation
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

# Other convenience functions. These grant us access to the global (pickle module) namespace and executable code.
Globals = Import(globals)
Locals = Import(locals)
Compile = Import(compile)

# The following can also be triggered from python syntax but do not have explicit builtins.
# Note: many arithmetric operators (basically any binary operation) isn't implemented here
# since their implementation involves control flow. While it is possible to call the relevant
# magic methods, this only gives part of the actual functionality.

def CallMethod(obj, attr, *args):
    """
    A convenience function for calling methods.
    """
    return GetAttr(obj, attr)(*args)

def GetItem(obj, attr):
    """
    The equivalent of obj[attr]
    """
    return CallMethod(obj, "__getitem__", attr)

def DelItem(obj, attr):
    """
    The equivalent of del obj[attr]
    """
    return CallMethod(obj, "__delitem__", attr)

# Note: unlike the normal ternary it is impossible to get lazy execution due to the lack of control flow in the pickle VM.
# By setting conditional to true_value a logical OR can also be evaluated.
def Ternary(conditional, true_value, false_value):
    """
    A simple ternary statement. Due to the limitations of pickling both branches will be executed
    But it is possible to have a conditional final result.
    """
    return GetItem((false_value, true_value), Bool(conditional))

# And these give us access to the global scope

def AssignGlobal(varname, value, module=None):
    """
    Assigns `value` to `varname` in the global namespace (to interact with exec and eval blocks)
    This is implemented as globals()[varname] = value
    This returns the global namespace
    """
    if module is None:
        namespace = Globals()
    else:
        namespace = GetAttr(GetModule(module), "__dict__")
    return SetItem(namespace, varname, value)

def LoadGlobal(varname, module=None):
    """
    Loads `varname` from the global namespace
    This is implemented as globals()[varname]
    """
    if module is None:
        namespace = Globals()
    else:
        namespace = GetAttr(GetModule(module), "__dict__")
    return GetItem(namespace, varname)

# Code execution fun times

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
        # Note: we don't do Import(exec) because exec's a keyword in py2 and would cause the parser to fail
        if globals and locals:
            return Imports("builtins", "exec")(string, globals, locals)
        elif globals:
            return Imports("builtins", "exec")(string, globals)
        else:
            return Imports("builtins", "exec")(string)

# And of course shell access. subprocess.popen would be more valid but produces bigger results

def System(string):
    """
    This will execute `string` as a shell command
    """
    return Imports("os", "system")(string)


# Interaction with the module system. This allows us to define and import modules at runtime, and use them inside
# the pickle.

def DeclareModule(name, retval=True):
    """
    Declares a module. This creates an empty module and
    inserts it in the sys.modules namespace,
    if retval is True then the module will be returned
    else sys.modules will be returned
    """
    #note: this could be more optimized using a temp local var.
    val = SetItem(
        Imports("sys", "modules"),
        name,
        Imports("imp", "new_module")(name)
    )
    return GetItem(val, name) if retval else val

def DefineModule(name, code, executor=Exec):
    """
    This 'defines' a module by executing a block of code in the namespace
    Of said module. Returns None
    """
    return executor(code, globals=Imports(name, "__dict__"), filename="<{0}>".format(name))

def GetModule(name):
    """
    This imports module `name`. Note that, if you ever need something contained in a module, it is more
    efficient to just use the native Import or Imports.
    """
    val = Import(__import__)(name)
    submodules = name.split(".")[1:]
    for submodule in submodules:
        val = GetAttr(val, submodule)
    return val

def Module(name, code, retval=True, executor=Exec):
    """
    This node creates a module at importing time.
    It simply takes the name of the module and the code in the module as a string.
    This is done by first declaring the module, and then defining it. If circular
    references between modules are problematic, the declaring and defining has
    to be ordered manually.

    it returns the module if retval is set to True, else it returns sys.modules
    """
    return Sequence(
        DeclareModule(name, retval),
        DefineModule(name, code, executor),
        reversed=True
    )
# And for some crazier Exec implementations

def ExecTranspile(string, foreign=(), globals=Globals(), locals=None, filename="<pickle>"):
    node = ast.parse(string, mode="exec")
    return TransPickler(foreign).visit(node)

class TransPickler(ast.NodeVisitor):
    def __init__(self, foreign):
        self.globals = set()
        self.foreign = foreign
        self.foreign_i = 0
        if PY2:
            import __builtin__
            self.imports = {name: ("__builtin__", name) for name in __builtin__.__dict__ if not name.startswith("_")}
        else:
            import builtins
            self.imports = {name: ("builtins", name) for name in builtins.__dict__ if not name.startswith("_")}

    def visit(self, node):
        if node is None:
            return node
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor is None:
            raise NotImplementedError(
                "python to pickle compilation does not support {0} node".format(
                    node.__class__.__name__))
        return visitor(node)

    def visit_list(self, nodes):
        return [self.visit(i) for i in nodes]

    # scopes

    def visit_Module(self, node):
        body = self.visit_list(node.body)
        return Sequence(*body)

    # variables

    def visit_Global(self, node):
        for name in node.names:
            if name in self.imports:
                raise NotImplementedError("Cannot make imported name global")
            self.globals.add(name)
        return Sequence()

    # namespace modifiers

    def visit_Name(self, node):
        # special: we hijack this if names in the format _%d are used. these indicate that special 
        # pickleast pieces must be inserted here which are not representable for transpilation
        if node.id.startswith("_") and node.id[1:].isdigit() and isinstance(node.ctx, ast.Load):
            return self.foreign[int(node.id[1:])]

        if isinstance(node.ctx, ast.Store):
            if node.id in self.imports:
                raise NotImplementedError("Assignment to import")
            elif node.id in self.globals:
                return AssignGlobal, node.id
            else:
                return Assign, node.id
        elif isinstance(node.ctx, ast.Load):
            if node.id in self.imports:
                return Imports(*self.imports[node.id])
            if node.id in self.globals:
                return LoadGlobal(node.id)
            else:
                return Load(node.id)
        else:
            raise NotImplementedError("Cannot pickle name {0}".format(node.id))

    def visit_NameConstant(self, node):
        return node.value

    # data literals

    def visit_Str(self, node):
        return node.s

    def visit_Num(self, node):
        return node.n

    def visit_Tuple(self, node):
        return tuple(self.visit_list(node.elts))

    def visit_List(self, node):
        return list(self.visit_list(node.elts))

    def visit_Dict(self, node):
        # a problem with this is that the dict / set items check for uniqueness of the given
        # PickleBase objects, not the actual values. This generally doesn't cause issues though as
        # all node objects we generate are unique.
        return dict(zip(self.visit_list(node.keys),
                        self.visit_list(node.values)))

    def visit_Set(self, node):
        return set(self.visit_list(node.elts))

    def visit_Ellipsis(self, node):
        return Ellipsis

    # statements

    def visit_Expr(self, node):
        return self.visit(node.value)

    def visit_Assign(self, node):
        assert len(node.targets) == 1
        left = self.visit(node.targets[0])
        right = self.visit(node.value)
        return left[0](*(left[1:]+(right,)))

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

    def visit_Import(self, node):
        return Sequence(*[Assign(alias.asname or alias.name, GetModule(alias.name)) for alias in node.names])

    def visit_ImportFrom(self, node):
        renames = []
        for alias in node.names:
            if alias.asname:
                renames.append(Assign(alias.asname, Imports(node.module, alias.name)))
            else:
                self.imports[alias.name] = (node.module, alias.name)

        return Sequence(*renames)

    def visit_Exec(self, node):
        return Exec(self.visit(node.body), self.visit(node.globals), self.visit(node.locals))

    def visit_BoolOp(self, node):
        # replace by ternary with a temp var.
        raise NotImplementedError()

    BINOP_MAP = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.LShift: operator.lshift,
        ast.RShift: operator.rshift,
        ast.BitOr: operator.or_,
        ast.BitXor: operator.xor,
        ast.BitAnd: operator.and_
    }
    def visit_BinOp(self, node):
        return Import(self.BINOP_MAP[node.op.__class__])(self.visit(node.left), self.visit(node.right))

    COMPARE_MAP = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
    }
    def visit_Compare(self, node):
        if len(node.comparators) > 1:
            raise SyntaxError("mutliple comparison is not supported")
        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
        op = node.ops[0]
        if op.__class__ == ast.In:
            return Import(operator.contains(right, left))
        elif op.__class__ == ast.NotIn:
            return Import(operator.not_)(Import(operator.contains)(right, left))
        else:
            return Import(self.COMPARE_MAP[op.__class__])(left, right)

    def visit_UnaryOp(self, node):
        value = self.visit(node.operand)
        if node.op.__class__ == UAdd:
            return Import(operator.pos)(value)
        elif node.op.__class__ == USub:
            return Import(operator.neg)(value)
        elif node.op.__class__ == Not:
            return Import(operator.not_)(value)
        elif node.op.__class__ == Invert:
            return Import(operator.invert)(value)
        else:
            raise Exception("Unreachable")


def ExecAst(string, globals=Globals(), locals=None, filename="<pickle>"):
    """
    Takes a string of python code and compiles it into an object that, after being serialized with the ASTPickler,
    will execute the python code when unserialized.

    The mechanism used for this is compiling the code to an AST, serializing this AST and then
    calling eval(compile()) on the ast.
    """
    node = ast.parse(string)
    node = PyAstCompiler().visit(node)
    node = Import(ast.fix_missing_locations)(node)
    # Explicit Eval(Compile()) here because you can't exec an ast
    return Eval(Compile(node, filename, "exec"), globals, locals)

class PyAstCompiler(ast.NodeTransformer):
    """
    Takes a python AST and returns an object hierarchy that, when pickled using the ASTPickler
    compresses in a more optimized format due to it calling the ast constructors directly.

    This is a more efficient way of embedding python ast's in pickles
    """
    def generic_visit(self, node):
        # Be more efficient while pickling the ast by just calling the constructors
        # Instead of using SetAttributes
        for field, old_value in ast.iter_fields(node):
            if isinstance(old_value, list):
                old_value[:] = [self.visit(i) if isinstance(i, ast.AST) else i for i in old_value]
            elif isinstance(old_value, ast.AST):
                setattr(node, field, self.visit(old_value))
        return Call(type(node), *[getattr(node, i) for i in node._fields])

def optimize_puts(p):
    """
    Optimize a pickle by assigning the low 256 BINPUT's
    to the most used gets.

    Should only be used for pickle protocol 1 - 3
    """
    counter = {}
    process = []
    prevnode = None
    for opcode, arg, pos in pickletools.genops(p):
        if prevnode is not None:
            process.append((pos, prevnode))
            prevnode = None
        if "GET" in opcode.name:
            if arg in counter:
                counter[arg] += 1
            else:
                counter[arg] = 1
            prevnode = opcode.name, arg, pos
        elif "PUT" in opcode.name:
            prevnode = opcode.name, arg, pos
        elif "MEMOIZE" in opcode.name:
            raise Exception("Memoize opcode detected, pickle version not supported")

    replmap = dict((key, i) for i, key in enumerate(sorted(counter.keys(), key=lambda x: -counter[x])))

    rv = []
    i = 0
    for newpos, (name, arg, pos) in process:
        rv.append(p[i:pos])
        newarg = replmap[arg]
        if "GET" in name:
            if newarg < 256:
                rv.append(pickle.BINGET + chr(newarg))
            else:
                rv.append(pickle.LONG_BINGET + pack("<i", newarg))
        elif "PUT" in name:
            if newarg < 256:
                rv.append(pickle.BINPUT + chr(newarg))
            else:
                rv.append(pickle.LONG_BINPUT + pack("<i", newarg))
        i = newpos
    rv.append(p[i:])
    return ''.join(rv)
