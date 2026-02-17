:mod:`corrupy.minimize` --- Python code minification
====================================================

.. module:: corrupy.minimize

The :mod:`minimize` module implements tools the minification of python code.

.. autofunction:: minimize

Utilities
---------

.. class:: DocstringRemover

An :class:`ast.NodeTransformer` that removes docstrings.

.. class:: DenseSourceGenerator

A :class:`.codegen.SourceGenerator` that generates very compact python code.
