import types
import sys
import pickle
import cPickle

class PickleBase(object):
    def __call__(self, *args):
        return Call(self, *args)

    def __getattr__(self, name):
        return Call(getattr, self, name)

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

class Call(PickleBase):
    def __init__(self, callable, *args):
        self.callable = callable
        self.args = args
    def serialize(self, pickler):
        pickler.save(self.callable)
        pickler.write(pickle.MARK)
        for i in self.args:
            pickler.save(i)
        pickler.write(pickle.TUPLE+pickle.REDUCE)
    def __repr__(self):
        if self.args:
            return "Call({}, {})".format(repr(self.callable), ", ".join(repr(arg) for arg in self.args))
        else:
            return "Call({})".format(repr(self.callable))

def DelAttr(self, obj, attr):
    return CallMethod(obj, "__delattr__", attr)

def DelItem(self, obj, attr):
    return CallMethod(obj, "__delitem__", attr)

def CallMethod(obj, attr, *args):
    return Call(Call(getattr, obj, attr), *args)

# Some objects lie about their actual __module__ and __name__
# Notable: types.FunctionType says it's __builtin__.function
special_cases = {types.FunctionType: ("FunctionType", "types")}

class Pickle(PickleBase):
    def __init__(self, obj):
        self.obj = obj
    def serialize(self):
        return "\x80\x02" + self.obj.serialize() + "."
    def __repr__(self):
        return "Pickle({})".format(repr(self.obj))

class Wrap(PickleBase):
    def __init__(self, obj):
        self.obj = obj
    def serialize(self, pickler):
        return pickler.save(self.obj)

class Import(Wrap):
    def __init__(self, obj):
        try:
            self.name, self.module = special_cases[obj]
        except:
            self.name = obj.__name__
            self.module = obj.__module__
    def serialize(self, pickler):
        return pickler.write("c{}\n{}\n".format(self.module, self.name))
    def __repr__(self):
        return "Import({}.{})".format(self.module, self.name)

class Imports(Import):
    def __init__(self, module, name):
        self.name = name
        self.module = module

class Sequence(PickleBase):
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

def Module(name, code):
    return Sequence(
                Import(types.FunctionType)(
                    Import(compile)("""
import imp, sys
{0} = imp.new_module("{0}")
exec {1} in {0}.__dict__
sys.modules["{0}"] = {0}""".format(name, repr(code)), 
                        "<pickle>", 
                        "exec"), 
                    Import(globals)(),
                    'exe'
                    )(),
                Imports("sys", "modules")[name])

def Exec(string):
    return Import(types.FunctionType)(
                Import(compile)(
                    "exec {} in globals()".format(repr(string)), 
                    "<pickle>", 
                    "exec"), 
                Import(globals)(),
                'exe'
                )()

#####################################
from cStringIO import StringIO

def dumps(obj):
    file = StringIO()
    AstPickler(file).dump(obj)
    return file.getvalue()

def optimize_dumps(origpickle):
    optipickle = dumps(Import(cPickle.loads)(Wrap(origpickle.encode("zlib")).decode("zlib")))
    origpickle = optipickle
    while len(optipickle) < len(origpickle):
        origpickle = optipickle
        optipickle = dumps(Import(cPickle.loads)(Wrap(origpickle.encode("zlib")).decode("zlib")))
    return origpickle

class AstPickler(pickle.Pickler):
    def save(self, obj):
        if isinstance(obj, PickleBase):
            return obj.serialize(self)
        pickle.Pickler.save(self, obj)



