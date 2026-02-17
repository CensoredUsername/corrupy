:mod:`corrupy.pickleast` --- Special pickle construction
========================================================

.. module:: corrupy.pickleast

The :mod:`pickleast` module provides tools for constructing special pickles capable of
executing code and performing other operations during the deserialization of python's
pickle object serialization format.

Technical Background
--------------------

The deserialization machinery of the pickle format is powerful enough to construct arbitrary
graphs of dynamically created python objects. Due to the dynamic nature, this means it is also
capable of doing a lot more than just that.

The pickle format can be conceptually seen as a programming language that targets a very
simple stack machine. It has instructions for loading types, constructing them, and memoizing
them. Crucially, it has an instruction intended for object creation that simply calls a value
on the stack with other values as arguments. This means we can not just construct objects, but
also call functions. And since we can load builtins like :func:`getitem`, this instruction can
be used to call object methods, do slice indexing, perform math, etc. The main limitation to
this is that there is no control flow in the execution. The pickle bytecode will be executed
linearly, and as such it is impossible to encode looping constructs in the native pickle
control flow.

This can be worked around by calling builtins like :func:`eval` and just storing the python
code as a string, but one can imagine that these functions would be blacklisted during
unpickling. Therefore, this module implements as much python functionality as possible in pure pickle bytecode.

Interface
---------

To embed special behaviour in a pickle bytestream, this module provides a set of types based on
the :class:`PickleBase` type which can be placed anywhere in a normal python datastructure. This
datastructure can then serialized using the special :class:`AstPickler` implementation which
will embed the special instructions into the bytestream.

.. autofunction:: dumps

.. autofunction:: dump

.. autoclass:: AstPickler

AST types
---------

.. class:: PickleBase

This is the abstract base class that all pickleast AST types derive from. When :class:`AstPickler`
encounters an instance of this class during serialization, it's functionality will be serialized
into the bytestream.

.. method:: __call__(*args, **kwargs)

Shorthand method for creating a :class:`Call` AST node. `PickleBase()(*args)` is identical to `Call(PickleBase(), *args)`

Basic operations
^^^^^^^^^^^^^^^^

These AST nodes all correspond to individual pickle bytecodes:

.. autoclass:: Wrap

.. autoclass:: Call

.. autoclass:: SetAttributes

.. autoclass:: Imports

.. autoclass:: Import

.. autoclass:: Sequence

.. autoclass:: SetItem

.. autoclass:: Assign

.. autoclass:: Load

Useful functions
^^^^^^^^^^^^^^^^

These AST nodes are all :class:`Import` instances of the relevant builtin function:

.. data:: List

.. data:: Dict

.. data:: Set

.. data:: Tuple

.. data:: Frozenset

.. data:: Str

.. data:: Int

.. data:: Bool

.. data:: Any

.. data:: All

.. data:: Map

.. data:: Zip

.. data:: HasAttr

.. data:: GetAttr

.. data:: SetAttr

.. data:: DelAttr

.. data:: IsInstance

.. data:: IsSubclass

.. data:: Iter

.. data:: Next

.. data:: Range

.. data:: Globals

.. data:: Locals

.. data:: Compile

Operation analogues
^^^^^^^^^^^^^^^^^^^

These AST nodes represent basic python operations that aren't built into the pickle machinery
and therefore constructed using builtin functions:

.. autofunction:: CallMethod

.. autofunction:: GetItem

.. autofunction:: DelItem

.. autofunction:: Ternary

.. autofunction:: AssignGlobal

.. autofunction:: LoadGlobal

Code execution
^^^^^^^^^^^^^^

These AST nodes allow arbitrary python code to be executed during the unpickling process:

.. autofunction:: Eval

.. autofunction:: Exec

.. autofunction:: ExecTranspile

.. autofunction:: ExecAst

Shell execution
^^^^^^^^^^^^^^^

The quickest proof for why you should not unpickle untrusted data.

.. autofunction:: System

Module manipulation
^^^^^^^^^^^^^^^^^^^

.. autofunction:: DeclareModule

.. autofunction:: DefineModule

.. autofunction:: GetModule

.. autofunction:: Module

Utilities
---------

.. autofunction:: pprint

.. autoclass:: AstPrinter
   :members: dump

.. autoclass:: TransPickler

.. autoclass:: PyAstCompiler

.. autofunction:: optimize

.. autofunction:: optimize_puts
