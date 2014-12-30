:mod:`picklemagic` --- Pickle data extraction
=============================================

.. module:: picklemagic

The :mod:`picklemagic` module implements tools for extracting data serialized in the python pickle format.

Technical Background
--------------------

The Python pickle module is a nice tool for storing data structures, as long as
the Python environment stays the same almost anything can be pickled. But if the
original enviroment in which a pickle was made is unknown? Then trying to find
out what data was serialized is a very cumbersome task and unpickling it is even
a security risk.

The :mod:`picklemagic` module aims to solve this problem. Taking advantage of
Python's dynamic nature, it extracts as much information as possible from
pickles and creates a data structure as close as possible to the original.

This is accomplished by generating any missing class and module definitions
at runtime. These objects however only hold data which could be recovered
from the unpickling process, they lack any implementation, and will therefore
be referred to as fake classes and modules.

This module uses this behaviour in two ways. :class:`FakeUnpickler` uses
it simply to extend the normal unpickler behaviour, creating fake modules
and classes when it encounters a definition it cannot find in the available
modules. This ensures that the resulting data structure is as close to the
original as possible. :class:`SafeUnpickler` however uses it to replace
the default Unpickler behaviour, replacing any class definition requested
by the pickle by a fake class. This ensures safety during the unpickling
process since the pickle cannot instantiate dangerous objects or call
dangerous functions during the unpickling process.

Fake classes and modules
^^^^^^^^^^^^^^^^^^^^^^^^

The mechanics of fake classes and modules are an important part of this module.

Fake classes get instantiated when the unpickling machinery encounters a request
to load a top-level object from a module. In a normal pickle this object should
either be a function or a class object. When the module cannot be found or the object cannot be found in the module, a fake class has to be inserted. This fake
class is then created using the settings of the used :class:`FakeClassFactory`,
during which the classes :attr:`__module__` attribute will be set to the module
the class would have resided in, and the :attr:`__name__` attribute will be set
to the name the class would have had.

A similar process happens for the generation of fake modules. These modules will
be generated when a :class:`FakeUnpickler` encounters a reference to an object
in an unknown module. When this happens, a fake module will be generated to house
the fake classes which would be contained by that module. When such a module is
created, it will automatically generate all necessary parent modules and add
itself to :data:`sys.modules` so it can be imported properly. It should be noted
though that :class:`SafeUnpickler` does not generate fake modules while importing
since it is forbidden from importing modules.

A problem with this approach can be that it's hard to write code to analyze the
created datastructures when the fake modules and classes are only created at
unpickling time. Therefore it is made possible for the user to create the necessary
fake modules beforehand, either by creating :class:`FakeModule` instances directly
or by using :func:`fake_package`. This function allows the user to define that
any modules in the given package exist, which works recursively, for example:

``import picklemagic
picklemagic.fake_package("foo")

import foo.bar.baz
print(foo.bar.baz)

>>> <module 'foo.bar.baz' (fake)>``

These can then be used to code with due to the special comparison behaviour of
fake modules and classes. This behaviour works as follows: A fake class is equal
to a fake module if it's qualified name matches the qualified name of the fake
module. This means that a fake class which says it has name ``bar`` in module ``foo``
compares equal to a fake module which identifies as ``foo.bar`` (this behaviour extends to hashing and isinstance/issubclass checking). This can then be
used as follows:

``import picklemagic
picklemagic.fake_package("foo")

import foo

def is_foo_bar(obj):
    if isinstance(obj, foo.bar):
        print("yes")

result = picklemagic.safe_loads(b"cfoo\nbar\n(tR.")
# This pickle results in a foo.bar instance

is_foo_bar(result)
>>> yes``

This means that you don't have to worry about definitions not existing in certain
pickles. You can call :func:`fake_package` and then just code as if everything in
the module actually existed.

Security Risks
^^^^^^^^^^^^^^

While :class:`SafeUnpickler` secures the unpickling process by denying the process
access to globals and objects in modules by replacing the wanted definitions with
fake classes which cannot do any harm, there are other possible security risks in
the pickle protocol. These vulnerabilities are persistent ideas and the pickle
extension registry. Although :class:`SafeUnpickler` allows subclassing of
:meth:`SafeUnpickler.persistent_id`, care should be taken that the objects returned
by it cannot be used for anything harmful. The same goes for the pickle extension
registry if enabled (documented in the Python :mod:`copyreg` module).

Module Interface
----------------

To simply analyze a pickle string, you can simply call :func:`load` or
:func:`safe_load`. Similarly if you want to analyze a pickle data stream, you
can call the :func:`loads` and :func:`safe_loads` functions. However if you
want more control over the missing class faking process, you can control
FakeClass creation directly using :class:`FakeClassFactory` and by subclassing
:class:`FakeClassType`. For more control over the unpickling process itself the
classes :class:`FakeUnpickler` and :class:`SafeUnpickler` can be used directly.

The :mod:`picklemagic` module provides the following functions to make simple
use more convenient

.. autofunction:: load

.. autofunction:: safe_load

.. autofunction:: loads

.. autofunction:: safe_loads

To ease automatic analysis, the :mod:`picklemagic` module provides the
following functions.

.. autofunction:: fake_package

.. autofunction:: remove_fake_package

The :mod:`picklemagic` module defines this Exception:

.. autoexception:: FakeUnpicklingError

Fake Classes
^^^^^^^^^^^^

The :mod:`picklemagic` module uses the following classes to provide the necessary
fake class definitions required by the fake unpickling process.

.. autoclass:: FakeClassType(name, bases, dict)

.. autoclass:: FakeClassFactory(special_cases, errors='strict', fake_metaclass=FakeClassType, default_bases=(object,))
   :members: __call__

Fake Modules
^^^^^^^^^^^^

The :mod:`picklemagic` module uses the following classees to implement the fake
modules generated by :func:`fake_package` and the fake unpickling process.

.. autoclass:: FakeModule
   :members: _remove

.. autoclass:: FakePackage

.. autoclass:: FakePackageLoader

Fake Unpicklers
^^^^^^^^^^^^^^^

These two classes do the actual work behind the fake unpickling process. 

.. autoclass:: FakeUnpickler

.. autoclass:: SafeUnpickler