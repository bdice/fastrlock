import sys
import os
import re
from setuptools import setup, Extension

with open('fastrlock/__init__.py') as f:
    VERSION = re.search(
        r'^__version__ \s* = \s* ["\'] ([0-9ab.]+) ["\']',
        f.read(), re.MULTILINE|re.VERBOSE).group(1)

BASEDIR = os.path.dirname(__file__)
PKGNAME = 'fastrlock'
PKGDIR = os.path.join(BASEDIR, PKGNAME)
MODULES = [filename[:-4] for filename in os.listdir(PKGDIR)
           if filename.endswith('.pyx')]


def has_option(name):
    if name in sys.argv[1:]:
        sys.argv.remove(name)
        return True
    return False


ext_args = {
    'define_macros': [('CYTHON_CLINE_IN_TRACEBACK', '1')],
}
if has_option('--without-assert'):
    ext_args['define_macros'].append(('CYTHON_WITHOUT_ASSERTIONS', None))


use_cython = has_option('--with-cython')
if not use_cython:
    if not all(os.path.isfile(os.path.join(PKGDIR, module_name+'.c'))
               for module_name in MODULES):
        print("NOTE: generated sources not available, need Cython to build")
        use_cython = True


cythonize = None
if use_cython:
    try:
        from Cython.Build import cythonize
        import Cython.Compiler.Version
        print("building with Cython " + Cython.Compiler.Version.version)
        source_extension = ".pyx"

        # Check Cython version for freethreading directive support
        from packaging.version import Version
        has_freethreading = Version(Cython.Compiler.Version.version) >= Version("3.1.0")
        if has_freethreading:
            print("Cython supports freethreading_compatible directive")
    except ImportError:
        print("WARNING: trying to build with Cython, but it is not installed")
        cythonize = None
        source_extension = ".c"
        has_freethreading = False
else:
    print("building without Cython")
    source_extension = ".c"
    has_freethreading = False


# Define module_slots for free-threading support when available
module_slots = None
try:
    import importlib.metadata
    from packaging.version import Version

    try:
        py_version = Version(importlib.metadata.version('python'))
        has_free_threading = hasattr(sys, 'get_gil_mode') or Version(py_version) >= Version('3.13')
    except (importlib.metadata.PackageNotFoundError, AttributeError):
        has_free_threading = hasattr(sys, 'get_gil_mode') or sys.version_info >= (3, 13)

    if has_free_threading:
        print("Detected Python with free-threading support")
        module_slots = [('Py_mod_gil', 'Py_MOD_GIL_NOT_USED')]
except ImportError:
    has_free_threading = False


ext_modules = [
    Extension(
        '%s.%s' % (PKGNAME, module_name),
        sources=[os.path.join(PKGNAME, module_name+source_extension)],
        py_limited_api=False,
        py_module_slots=module_slots,
        **ext_args)
    for module_name in MODULES]


if cythonize is not None:
    compiler_directives = {
        'binding': True,
        'language_level': '3',
    }

    if has_freethreading:
        compiler_directives['freethreading_compatible'] = True

    ext_modules = cythonize(ext_modules, compiler_directives=compiler_directives)


def read_file(filename):
    f = open(os.path.join(BASEDIR, filename))
    try:
        return f.read()
    finally:
        f.close()


long_description = '\n\n'.join([
    read_file(text_file)
    for text_file in ['README.rst', 'CHANGES.rst']])


setup(
    name="fastrlock",
    version=VERSION,
    author="Stefan Behnel",
    author_email="stefan_ml@behnel.de",
    url="https://github.com/scoder/fastrlock",
    license='MIT style',
    description="Fast, re-entrant optimistic lock implemented in Cython",
    long_description=long_description,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Cython',
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
        'Topic :: Software Development',
    ],

    packages=[PKGNAME],
    package_data={PKGNAME: ['*.pyx', '*.pxd', '*.pxi']},
    ext_modules=ext_modules,
    zip_safe=False,

    # support 'test' target if setuptools/distribute is available
    test_suite='fastrlock.tests.suite',
)
