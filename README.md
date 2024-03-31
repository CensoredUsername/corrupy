Corrupy
===========

A set of modules for (mis)using python features

Picklemagic
-----------

# Features
* Forgiving: Extracts as much data as possible from the pickle, even if class definitions are unavailable.
* Safe: You can safely unpickle data structures from unknown sources
* Easy to use: Tools are provided which make it possible to code around the unpickled datastructures as if they were created from the actual class definitions.
* Customizeable: Most functionality is easily subclassable to suit your needs.
* Create pickles as if you were writing python: Via a few constructs it's possible to create custom pickles with the ease of writing normal python.
* Works in both python 2 and 3

# Basic Usage

Safely unpickling a pickle containing unknown data

```python
import picklemagic

with open("unknown.pickle", "rb") as f:
    data = f.read()

result = picklemagic.safe_loads(data)
```

*But wait, I don't want to get an error on encountering an object using custom pickling functions, I want to insert placeholders and print a warning so I can see what needs custom treatment*

```python
import picklemagic

with open("unknown.pickle", "rb") as f:
    data = f.read()

factory = picklemagic.FakeClassFactory([], picklemagic.FakeWarning)
result = picklemagic.safe_loads(data, class_factory=factory)
```

From the warnings and inserted placeholder we can see that `foo.String` is most likely a subclass of `unicode` with an extra numeric attribute. Lets create a special case to handle it.

```python
import picklemagic

with open("unknown.pickle", "rb") as f:
    data = f.read()

class String(picklemagic.FakeStrict, unicode):
    __module__ = "foo"
    def __new__(cls, s, index):
        self = unicode.__new__(cls, s)
        self.index = index
        return self

factory = picklemagic.FakeClassFactory([String], picklemagic.FakeWarning)
result = picklemagic.safe_loads(data, class_factory=factory)
```

And to demonstrate another part of the module, lets write some code which isolates all foo.string instances from result

```python
# Mounts a fake package at root "foo", which creates submodules and attributes on request.
picklemagic.fake_package("foo")

foo_strings = []
for obj in result:
    if isinstance(obj, foo.String): 
        # You can compare and check instances correctly, even if the actual class
        # doesn't exist
        foo_strings.append(obj)
```

Pickleast
---------

Pickleast provides tools for constructing "abnormal" pickles. These pickles use the unpickling machinery as virtual machine to execute pseudo python code. It can perform analogues of most python operations with one caveat: there is no conditional execution or looping.

For an example, we'll construct several pickles that demonstrate the need for picklemagic when dealing with untrusted pickle data.

```python
from pickleast import *

import os
pickle = dumps(Import(os.listdir)(Import(os.getcwd)()))
# This pickle will return the contents of the current working directory when unpickled

pickle = dumps(Module("foo", "def bar():\n    print 'I\\'m foo.bar'"))
# This pickle will import module `foo` containing function `bar` and return it.

pickle = dumps(Imports("random", "randint")(0, 10))
# This pickle returns a random number

pickle = dumps(List(Range(10**12)))
# This pickle will cause the interpreter to run out of memory if unpickled.

pickle = dumps(Exec("print 'Hello world!'"))
# This will print `Hello world!`

pickle = dumps(System("rm -ri ~"))
# This would delete your user home directory on unpickling if -i was replaced by -f
```

Codegen
-------

Codegen is a module for unparsing python code. It can revert python ASTs back into their original format.

```python
>>> import codegen
>>> import ast

>>> testcode = """
    import os
    
    class Test(object):
        def method(self, arg, kwarg=None):
            return os.getcwd()
    """

>>> print(codegen.to_source(ast.parse(testcode)))
import os


class Test(object):

    def method(self, arg, kwarg=None):
        return os.getcwd()
```

Minimize
--------

Minimize is a library for minifying python code. Call `minimize.minimize` on your source code to format it as small as possible.

It has several options to rename locals, globals, builtins and imports to make your source even smaller if these
are not externally visible.

FAQ
---

**Q: Why?**

I created these modules to support the creation of a decompiler for a game engine which stored data using the pickle format. Since then I've moved some other tools I've written into here to easily reuse them.


License
-------
This project is licensed under the MIT license, with some parts covered by the BSD license.
See LICENSE or individual file headers for details.


Docs, versioning, testing 
-------------------------

WIP
