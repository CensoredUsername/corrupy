# Copyright (c) 2014 CensoredUsername

# This module provides tools for constructing special pickles


import types
import sys
import pickle
import cPickle

# Main API
from cStringIO import StringIO

def dumps(obj):
    """
    Create a pickle from an object with special behaviour for PickleAst nodes
    """
    file = StringIO()
    AstPickler(file).dump(obj)
    return file.getvalue()

def optimize(origpickle):
    """
    'optimizes' a pickle by embedding a zlib compressed pickle inside the pickle
    """
    return dumps(Import(pickle.loads)(Wrap(origpickle.encode("zlib")).decode("zlib")))

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
                pickler.write(pickle.MARK)
                pickler.save(None)
                pickler.save(self.kwargs)
                pickler.write(pickle.TUPLE+pickle.BUILD)
            else:
                pickler.save(self.callable)
                pickler.write(pickle.MARK)
                for i in self.args:
                    pickler.save(i)
                pickler.write(pickle.TUPLE+pickle.REDUCE)

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

class Import(Wrap):
    """
    This wrapper class will return obj at unpickling time

    Requirements: obj is a top level object in a module
    """
    # Some objects lie about their actual __module__ and __name__
    # Notable: types.FunctionType says it's __builtin__.function
    special_cases = {types.FunctionType: ("FunctionType", "types")}

    def __init__(self, obj):
        try:
            self.name, self.module = self.special_cases[obj]
        except KeyError:
            self.name = obj.__name__
            self.module = obj.__module__

    def serialize(self, pickler):
        return pickler.write("c{}\n{}\n".format(self.module, self.name))

    def __repr__(self):
        return "Import({}.{})".format(self.module, self.name)

class Imports(Import):
    """
    This class will return the object `name` in module `module
    at unpickling time
    """
    def __init__(self, module, name):
        self.name = name
        self.module = module

class Sequence(PickleBase):
    """
    This class represents a series of objects, where only the last return
    value of the sequence will be returned at unpickling time
    """
    def __init__(self, *objects):
        self.objects = objects[:-1]
        self.result = objects[-1]

    def serialize(self, pickler):
        pickler.write(pickle.MARK)
        for obj in self.objects:
            pickler.save(obj)
        pickler.write(pickle.POP_MARK)
        pickler.save(self.result)

    def __repr__(self):
        return "Sequence({}|{})".format(", ".join(repr(i) for i in self.objects), repr(self.result))

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
Apply = Import(apply)
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

# Should add some kind of "variable" manipulation using the pickle memo

def Module(name, code):
    """
    This node creates a module at importing time.
    It simply takes the name of the module and the code in the module as a string

    it returns the module
    """
    return Sequence(
                Import(types.FunctionType)(
                    Compile("""
import imp, sys
{0} = imp.new_module("{0}")
exec {1} in {0}.__dict__
sys.modules["{0}"] = {0}""".format(name, repr(code)), 
                        "<pickle>", 
                        "exec"), 
                    Globals(),
                    'exe'
                    )(),
                Imports("sys", "modules")[name])

def Exec(string):
    """
    This node executes `string` in the global namespace (this will usually be the
    pickle module namespace)

    This is implemented by exec'ing the code within a dynamically created anonymous function

    It returns None
    """
    return Import(types.FunctionType)(
                Compile(
                    "exec {} in globals()".format(repr(string)), 
                    "<pickle>", 
                    "exec"), 
                Globals(),
                'exe'
                )()

def Eval(code):
    """
    This node executes `code` in the global (pickle module) namespace and returns the result
    """
    return Import(eval)(code, Globals())
