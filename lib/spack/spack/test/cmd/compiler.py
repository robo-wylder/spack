# Copyright 2013-2020 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import os
import shutil

import pytest

import llnl.util.filesystem
import spack.main
import spack.version

compiler = spack.main.SpackCommand('compiler')


@pytest.fixture
def no_compilers_yaml(mutable_config):
    """Creates a temporary configuration without compilers.yaml"""

    for scope, local_config in mutable_config.scopes.items():
        compilers_yaml = os.path.join(
            local_config.path, scope, 'compilers.yaml'
        )
        if os.path.exists(compilers_yaml):
            os.remove(compilers_yaml)


@pytest.fixture
def mock_compiler_version():
    return '4.5.3'


@pytest.fixture()
def mock_compiler_dir(tmpdir, mock_compiler_version):
    """Return a directory containing a fake, but detectable compiler."""

    tmpdir.ensure('bin', dir=True)
    bin_dir = tmpdir.join('bin')

    gcc_path = bin_dir.join('gcc')
    gxx_path = bin_dir.join('g++')
    gfortran_path = bin_dir.join('gfortran')

    gcc_path.write("""\
#!/bin/sh

for arg in "$@"; do
    if [ "$arg" = -dumpversion ]; then
        echo '%s'
    fi
done
""" % mock_compiler_version)

    # Create some mock compilers in the temporary directory
    llnl.util.filesystem.set_executable(str(gcc_path))
    gcc_path.copy(gxx_path, mode=True)
    gcc_path.copy(gfortran_path, mode=True)

    return str(tmpdir)


@pytest.mark.regression('11678,13138')
def test_compiler_find_without_paths(no_compilers_yaml, working_env, tmpdir):
    with tmpdir.as_cwd():
        with open('gcc', 'w') as f:
            f.write("""\
#!/bin/bash
echo "0.0.0"
""")
        os.chmod('gcc', 0o700)

    os.environ['PATH'] = str(tmpdir)
    output = compiler('find', '--scope=site')

    assert 'gcc' in output


def test_compiler_remove(mutable_config, mock_packages):
    args = spack.util.pattern.Bunch(
        all=True, compiler_spec='gcc@4.5.0', add_paths=[], scope=None
    )
    spack.cmd.compiler.compiler_remove(args)
    compilers = spack.compilers.all_compiler_specs()
    assert spack.spec.CompilerSpec("gcc@4.5.0") not in compilers


def test_compiler_add(
        mutable_config, mock_packages, mock_compiler_dir, mock_compiler_version
):
    # Compilers available by default.
    old_compilers = set(spack.compilers.all_compiler_specs())

    args = spack.util.pattern.Bunch(
        all=None,
        compiler_spec=None,
        add_paths=[mock_compiler_dir],
        scope=None
    )
    spack.cmd.compiler.compiler_find(args)

    # Ensure new compiler is in there
    new_compilers = set(spack.compilers.all_compiler_specs())
    new_compiler = new_compilers - old_compilers
    assert any(c.version == spack.version.Version(mock_compiler_version)
               for c in new_compiler)


@pytest.fixture
def clangdir(tmpdir):
    """Create a directory with some dummy compiler scripts in it.

    Scripts are:
      - clang
      - clang++
      - gfortran-8

    """
    with tmpdir.as_cwd():
        with open('clang', 'w') as f:
            f.write("""\
#!/bin/sh
if [ "$1" = "--version" ]; then
    echo "Apple clang version 11.0.0 (clang-1100.0.33.16)"
    echo "Target: x86_64-apple-darwin18.7.0"
    echo "Thread model: posix"
    echo "InstalledDir: /dummy"
else
    echo "clang: error: no input files"
fi
""")
        shutil.copy('clang', 'clang++')

        with open('gfortran-8', 'w') as f:
            f.write("""\
#!/bin/sh
if [ "$1" = "--version" ]; then
    echo "GNU Fortran (GCC) 8.4.0 20120313 (Red Hat 8.4.0-1)"
    echo "Copyright (C) 2010 Free Software Foundation, Inc.
else
    echo "gfortran-8: fatal error: no input files"
    echo "compilation terminated."
fi
""")
        os.chmod('clang', 0o700)
        os.chmod('clang++', 0o700)
        os.chmod('gfortran-8', 0o700)

    yield tmpdir


@pytest.mark.regression('17590')
def test_compiler_find_mixed_suffixes(
        no_compilers_yaml, working_env, clangdir):
    """Ensure that we'll mix compilers with different suffixes when necessary.
    """
    os.environ['PATH'] = str(clangdir)
    output = compiler('find', '--scope=site')

    assert 'clang' in output

    config = spack.compilers.get_compiler_config('site', False)

    new = config[-1]['compiler']
    assert new['spec'] == "apple-clang@11.0.0"
    assert new['paths'] == {
        'cc': str(clangdir.join('clang')),
        'cxx': str(clangdir.join('clang++')),
        'f77': str(clangdir.join('gfortran-8')),
        'fc': str(clangdir.join('gfortran-8')),
    }


@pytest.mark.regression('17590')
def test_compiler_find_prefer_no_suffix(
        no_compilers_yaml, working_env, clangdir):
    """Ensure that we'll pick 'clang' over 'clang-gpu' when there is a choice.
    """
    with clangdir.as_cwd():
        shutil.copy('clang', 'clang-gpu')
        shutil.copy('clang++', 'clang++-gpu')
        os.chmod('clang-gpu', 0o700)
        os.chmod('clang++-gpu', 0o700)

    os.environ['PATH'] = str(clangdir)
    output = compiler('find', '--scope=site')

    assert 'clang' in output

    config = spack.compilers.get_compiler_config('site', False)

    new = config[-1]['compiler']
    assert new['spec'] == "apple-clang@11.0.0"
    assert new['paths']['cc'] == str(clangdir.join('clang'))
    assert new['paths']['cxx'] == str(clangdir.join('clang++'))
