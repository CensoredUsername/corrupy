# Copyright (c) 2014 CensoredUsername

# This module provides tools for constructing special pickles


import pickle
import cPickle
import pickletools

# Main API
import itertools
import types
import sys
import zlib
from cStringIO import StringIO

def dumps(obj, protocol=2):
    """
    Create a pickle from an object with special behaviour for PickleAst nodes
    """
    file = StringIO()
    AstPickler(file, protocol).dump(obj)
    return file.getvalue()

def optimize(origpickle, protocol=2):
    """
    'optimizes' a pickle by embedding a zlib compressed pickle inside the pickle
    """
    origpickle = pickletools.optimize(origpickle)
    return pickletools.optimize(
               dumps(
                   Import(pickle.loads)(
                       Wrap(
                           zlib.compress(
                               pickletools.optimize(origpickle), 
                               9)
                           ).decode("zlib")
                       ),
                   2)
               )

class AstPickler(pickle.Pickler):
    """
    Pickler class with special behaviour for PickleBase instances
    """
    def save(self, obj):
        if isinstance(obj, PickleBase):
            return obj.serialize(self)
        pickle.Pickler.save(self, obj)

# The base class all pickleast objects inherit from

class PickleBase(object):
    def __call__(self, *args, **kwargs):
        return Call(self, *args, **kwargs)

    def __getattr__(self, name):
        return GetAttr(self, name)

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

    def __pos__(self):
        return CallMethod(self, "__pos__")
    def __neg__(self):
        return CallMethod(self, "__neg__")
    def __abs__(self):
        return CallMethod(self, "__abs__")
    def __invert__(self):
        return CallMethod(self, "__invert__")

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

    def __getattr__(self, name):
        return Call(getattr, self, name)
    def __delattr__(self, name):
        return Call(delattr, self, name)

    def __getitem__(self, key):
        return CallMethod(self, "__getitem__", key)

    def __contains__(self, item):
        return CallMethod(self, "__contains__")

    def serialize(self, picker):
        return NotImplementedError()

class Wrap(PickleBase):
    """
    A simple wrapper class which transforms obj into a PickleBase so the magic methods
    of picklebase can be used.
    """
    def __init__(self, obj):
        self.obj = obj
    def serialize(self, pickler):
        return pickler.save(self.obj)

# from the pickle VM opcodes a few basic operations can be constructed
# loading an arbitrary object from a module
# Calling something with an arbitrary amount of arguments
# either calling obj.__setattr__ or obj.__dict__.update using a dict of kwargs
# creating a series of objects and only returning the last one
# Storing and loading variables from the memo
# These base operations are implemented here

class Call(PickleBase):
    """
    This operation represents either calling an object on the pickle VM stack or 
    Calling __setattr__ or __dict__.update on it depending on what arguments are given.

    If this is called with an object and a set of positional arguments (or no arguments),
    the object will be called with these arguments at unpickling time.

    If it is however called with keyword arguments, it will call __dict__.update with these
    keyword arguments and return the object.
    """
    def __init__(self, callable, *args, **kwargs):
        self.callable = callable
        if args and kwargs:
            raise ValueError("Call() cannot take both initialization arguments and attribute setting keyword arguments")
        self.args = args
        self.kwargs = kwargs

    def serialize(self, pickler):
            if self.kwargs:
                pickler.save(self.callable)
                pickler.save((None, self.kwargs))
                pickler.write(pickle.BUILD)
            else:
                pickler.save(self.callable)
                pickler.save(tuple(self.args))
                pickler.write(pickle.REDUCE)

    def __repr__(self):
        if self.kwargs:
            return "Call({}, {})".format(repr(self.callable), 
                                         ", ".join(key + "=" + repr(value) for key, value in self.kwargs.iteritems()))
        else:
            if self.args:
                return "Call({}, {})".format(repr(self.callable), 
                                             ", ".join(repr(arg) for arg in self.args))
            else:
                return "Call({})".format(repr(self.callable))


class Imports(Wrap):
    """
    This class will return the object `name` in module `module
    at unpickling time
    """
    def __init__(self, module, name, cache=True):
        self.name = name
        self.module = module
        self.cache = cache

    def serialize(self, pickler):
        if self.cache:
            tup = (self.module, self.name)
            if tup in pickler.memo:
                index = pickler.memo[tup]
                pickler.write(pickler.get(index))
            else:
                memo_len = len(pickler.memo)
                pickler.memo[tup] = memo_len
                pickler.write(pickle.GLOBAL + self.module + '\n' + self.name  + '\n')
                pickler.write(pickler.put(memo_len))
        else:
            pickler.write(pickle.GLOBAL + self.module + '\n' + self.name  + '\n')

    def __repr__(self):
        return "Import({}.{})".format(self.module, self.name)

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

    def serialize(self, pickler):
        pickler.write(pickle.MARK)
        for obj in self.objects:
            pickler.save(obj)
        pickler.write(pickle.POP_MARK)
        pickler.save(self.result)

    def __repr__(self):
        return "Sequence({}|{})".format(", ".join(repr(i) for i in self.objects), repr(self.result))

class SetItem(PickleBase):
    """
    This class provides the equivalent of object[key] = value.
    This returns object
    """
    def __init__(self, object, key, value):
        self.obj = object
        self.key = key
        self.value = value

    def serialize(self, pickler):
        pickler.save(self.obj)
        pickler.save(self.key)
        pickler.save(self.value)
        pickler.write(pickle.SETITEM)

    def __repr__(self):
        return "{0}[{1}] = {2}".format(repr(self.obj), repr(self.key), repr(self.value))

class Assign(PickleBase):
    """
    This class stores `value` in `varname`. This is implemented as
    pushing the value on to the memo.
    This returns `value`.
    """
    def __init__(self, varname, value):
        if '\n' in varname or '\r' in varname:
            raise ValueError("Don't use line breaks in a varname") 
        self.varname = varname
        self.value = value

    def serialize(self, pickler):
        pickler.save(self.value)
        if self.varname in pickler.memo:
            pickler.write(pickler.put(pickler.memo[self.varname]))
        else:
            memo_len = len(pickler.memo)
            pickler.memo[self.varname] = memo_len
            pickler.write(pickler.put(memo_len))

    def __repr__(self):
        return "{0} = {1}".format(self.varname, repr(self.value))

class Load(PickleBase):
    """
    This class loads the `value` from `varname`.
    This is implemented by getting the value from the memo.
    This returns `value`
    """
    def __init__(self, varname):
        if '\n' in varname or '\r' in varname:
            raise ValueError("Don't use line breaks in a varname") 
        self.varname = varname

    def serialize(self, pickler):
        if self.varname not in self.memo:
            raise ValueError("attempted to use variable {1} but it hasn't been defined yet".format(varname))
        pickler.write(pickler.get(pickler.memo[self.varname]))

    def __repr__(self):
        return self.varname

def AssignGlobal(varname, value):
    """
    Assigns `value` to `varname` in the global namespace (to interact with exec and eval blocks)
    This is implemented as globals()[varname] = value
    THis returns `value`
    """
    return SetItem(Globals(), varname, value)[varname]

def LoadGlobal(varname):
    """
    Loads `varname` from the global namespace
    This is implemented as globals()[varname]
    """
    return Globals()[varname]


# From here on we define sets of convenience functions and wrappers useful for making easy pickle programs

# Data structure wrappers
List = Import(list)
Dict = Import(dict)
Set = Import(set)
Tuple = Import(tuple)
Frozenset = Import(frozenset)

# Functional programming
Any = Import(any)
All = Import(all)
Map = Import(map)
Zip = Import(zip)
Reduce = Import(reduce)

# Imspection
HasAttr = Import(hasattr)
GetAttr = Import(getattr)
SetAttr = Import(setattr)
DelAttr = Import(delattr)
IsInstance = Import(isinstance)
IsSubclass = Import(issubclass)

# Iterators
Iter = Import(iter)
Next = Import(next)

# Other convenience functions
Globals = Import(globals)
Locals = Import(locals)
Compile = Import(compile)

# Setitem needs implementation

def DelItem(self, obj, attr):
    # Since you can't save the return value of del a[i] this is necessary
    return CallMethod(obj, "__delitem__", attr)

def CallMethod(obj, attr, *args):
    return GetAttr(obj, attr)(*args)

# Specials

def DeclareModule(name):
    return SetItem(
               Imports("sys", "modules"), 
               name, 
               Imports("imp", "new_module")(name)
           )[name]

def DefineModule(name, code):
    code = '\n'.join(line for line in code.splitlines() if line.split("#")[0].strip())

    return Sequence(
               AssignGlobal("_c", code),
               AssignGlobal("_m", GetModule(name)),
               Import(types.FunctionType)(
                   Compile("exec _c in _m.__dict__", "<{0}>".format(name), "exec"),
                   Globals(),
                   'exe'
                   )()
               )

def GetModule(name):
    return Imports("__builtin__", "__import__")(name)

def Module(name, code):
    """
    This node creates a module at importing time.
    It simply takes the name of the module and the code in the module as a string

    it returns the module
    """
    return Sequence(
                DeclareModule(name),
                DefineModule(name, code),
                GetModule(name)
                )

def Exec(string):
    """
    This node executes `string` in the global namespace (this will usually be the
    pickle module namespace)

    This is implemented by exec'ing the code within a dynamically created anonymous function

    It returns None
    """
    return Sequence(
               AssignGlobal("_c", string),
               Import(types.FunctionType)(
                   Compile(
                       "exec _c in globals()", 
                       "<pickle>", 
                       "exec"), 
                   Globals(),
                   'exe'
                   )()
               )

def Eval(code):
    """
    This node executes `code` in the global (pickle module) namespace and returns the result
    """
    return Import(eval)(code, Globals())
